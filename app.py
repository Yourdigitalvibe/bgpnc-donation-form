from flask import Flask, render_template, request, jsonify, session
from decouple import config
import stripe
import logging
import os
from datetime import datetime

app_url = os.environ.get('APP_URL', 'http://127.0.0.1:5002')

app = Flask(__name__)
app.secret_key = config('FLASK_SECRET_KEY')
stripe.api_key = config('STRIPE_SECRET_KEY')

# Configure logging to console
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

@app.route('/')
def index():
    return render_template('index.html', stripe_publishable_key=config('STRIPE_PUBLISHABLE_KEY'))

@app.route('/test')
def test():
    return "Hello, World!"

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        data = request.form
        logging.debug(f"Form data received: {data}")

        total_amount = int(float(data['total_amount']) * 100)  # Convert to cents
        first_name = data['firstName']
        last_name = data['lastName']
        name = f"{first_name} {last_name}"
        email = data['email']
        note = data.get('note', '')
        frequency = data['recurring']
        funds = data.getlist('fund[]')
        amounts = data.getlist('fund_amount[]')

        # Store first name in session for success page
        session['first_name'] = first_name
        logging.debug(f"Stored first_name in session: {first_name}")

        # Fund descriptions
        fund_descriptions = {
            'tithes': 'Tithes',
            'offering': 'Offering',
            'give3': 'Give 3 to BGP',
            'sister-connect': 'BGP Sister Connect',
            'brother-connect': 'BGP Brother Connect',
            'singles-connect': 'BGP Singles Connect',
            'marriage-connect': 'BGP Marriage Connect',
            'other': 'Other'
        }

        # Build metadata for fund tracking
        metadata = {
            'name': name,
            'email': email,
            'giving_type': frequency,
            'total_amount': f"${float(data['total_amount']):.2f}",
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        # Add each fund allocation to metadata
        for i, (fund, amount) in enumerate(zip(funds, amounts)):
            if float(amount) > 0:
                fund_name = fund_descriptions.get(fund, 'Other')
                metadata[f'fund_{i+1}_name'] = fund_name
                metadata[f'fund_{i+1}_amount'] = f"${float(amount):.2f}"
        
        # Add note to metadata if provided
        if note:
            metadata['note'] = note

        # Build description
        fund_allocations = [f"{fund_descriptions.get(fund, 'Other')}: ${amount}" 
                          for fund, amount in zip(funds, amounts) if float(amount) > 0]
        description = f"Offering from {name} - Funds: {'; '.join(fund_allocations)}" if fund_allocations else f"Offering from {name}"
        if note:
            description += f" - Note: {note}"
            
        logging.debug(f"Payment description: {description}")
        logging.debug(f"Metadata: {metadata}")

        if frequency == 'one-time':
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {
                            'name': 'BGPNC Offering',
                            'description': description,
                        },
                        'unit_amount': total_amount,
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=f'{app_url}/success',
                cancel_url=f'{app_url}/cancel',
                customer_email=email,
                metadata=metadata
            )
        else:  # Monthly
            customer = stripe.Customer.create(
                email=email, 
                name=name,
                metadata=metadata
            )
            product = stripe.Product.create(
                name='BGPNC Monthly Offering', 
                description=description,
                metadata=metadata
            )
            price = stripe.Price.create(
                product=product.id,
                unit_amount=total_amount,
                currency='usd',
                recurring={'interval': 'month'},
                metadata=metadata
            )
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{'price': price.id, 'quantity': 1}],
                mode='subscription',
                success_url=f'{app_url}/success',
                cancel_url=f'{app_url}/cancel',
                customer=customer.id,
                metadata=metadata
            )

        logging.debug(f"Checkout session created: {checkout_session.id}")
        return jsonify({'id': checkout_session.id})

    except Exception as e:
        logging.error(f"Error in create_checkout_session: {str(e)}")
        return jsonify(error=str(e)), 500

@app.route('/success')
def success():
    first_name = session.get('first_name', 'Friend')
    return render_template('success.html', first_name=first_name)

@app.route('/cancel')
def cancel():
    return render_template('cancel.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug='PRODUCTION' not in os.environ)
