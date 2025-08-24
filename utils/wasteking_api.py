import os
import requests
import json
from datetime import datetime

# WasteKing API Configuration - NO HARDCODING
BASE_URL = os.getenv('WASTEKING_BASE_URL', 'https://wk-smp-api-dev.azurewebsites.net')
ACCESS_TOKEN = os.getenv('WASTEKING_ACCESS_TOKEN', 'wk-KZPY-tGF-@d.Aby9fpvMC_VVWkX-GN.i7jCBhF3xceoFfhmawaNc.RH.G_-kwk8*')

def wasteking_request(endpoint, payload, method="POST"):
    """WasteKing API request function - NO HARDCODING"""
    try:
        url = f"{BASE_URL}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "x-wasteking-request": ACCESS_TOKEN
        }
        
        print(f"🌐 API REQUEST: {method} {url}")
        print(f"📦 PAYLOAD: {json.dumps(payload, indent=2)}")
        
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=15)
        else:
            response = requests.get(url, params=payload, headers=headers, timeout=15)
        
        print(f"📊 RESPONSE: {response.status_code} - {response.text}")
        
        if response.status_code in [200, 201]:
            try:
                return {"success": True, **response.json()}
            except:
                return {"success": True, "response": response.text}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "response": response.text}
            
    except Exception as e:
        print(f"❌ API ERROR: {str(e)}")
        return {"success": False, "error": str(e)}

def create_booking():
    """Step 1: Create booking reference - NO HARDCODING"""
    print("📋 STEP 1: Creating booking...")
    payload = {"type": "chatbot", "source": "wasteking.co.uk"}
    result = wasteking_request("api/booking/create", payload)
    
    if result.get('success'):
        booking_ref = result.get('bookingRef') or result.get('booking_ref')
        print(f"✅ BOOKING REF: {booking_ref}")
        return {"success": True, "booking_ref": booking_ref}
    return result

def get_pricing(booking_ref, postcode, service, skip_type=None):
    """Step 2: Get pricing with booking ref - REAL API PRICES ONLY, NO HARDCODING"""
    print(f"💰 STEP 2: Getting REAL price for {service} {skip_type or 'default'} at {postcode}...")
    
    payload = {
        "bookingRef": booking_ref,
        "search": {
            "postCode": postcode,
            "service": service
        }
    }
    
    # Add type parameter if provided - CRITICAL FOR MAV WITH TYPE
    if skip_type:
        payload["search"]["type"] = skip_type
        print(f"🔧 INCLUDING TYPE PARAMETER: {skip_type}")
    
    result = wasteking_request("api/booking/update", payload)
    
    if result.get('success'):
        # Extract REAL price from resultItems array for specific postcode - NO HARDCODING
        result_items = result.get('resultItems', [])
        
        print(f"🔍 API returned {len(result_items)} REAL price options for {postcode}:")
        for item in result_items:
            print(f"   {item.get('type')}: {item.get('price')}")
        
        # Find the exact type requested if specified
        if skip_type:
            for item in result_items:
                if item.get('type') == skip_type:
                    price = item.get('price')
                    if price and price != 'call' and price != '£0.00':
                        print(f"✅ FOUND REAL PRICE {skip_type} for {postcode}: {price}")
                        return {"success": True, "price": price, "type": skip_type}
        
        # If no specific type or type not found, get first available priced item
        for item in result_items:
            price = item.get('price')
            item_type = item.get('type')
            if price and price != 'call' and price != '£0.00':
                print(f"✅ FOUND REAL PRICE {item_type} for {postcode}: {price}")
                return {"success": True, "price": price, "type": item_type}
        
        print(f"❌ No fixed REAL prices available for {postcode} - all require phone quote")
        return {"success": False, "error": f"No fixed prices for {postcode} - API returned 'call' only"}
    
    print(f"❌ API failed for {postcode}")
    return {"success": False, "error": "Pricing API call failed"}

def update_booking_details(booking_ref, customer_data):
    """Step 3: Update booking with customer details - NO HARDCODING"""
    print("📝 STEP 3: Updating customer details...")
    payload = {
        "bookingRef": booking_ref,
        "customer": {
            "firstName": customer_data.get('firstName', ''),
            "lastName": customer_data.get('lastName', ''),
            "phone": customer_data.get('phone', ''),
            "emailAddress": customer_data.get('email', ''),
            "addressPostcode": customer_data.get('postcode', '')
        },
        "service": {
            "date": customer_data.get('date', ''),
            "time": "am",
            "placement": "drive",
            "notes": f"{customer_data.get('service', '')} booking"
        }
    }
    result = wasteking_request("api/booking/update", payload)
    
    if result.get('success'):
        print("✅ DETAILS UPDATED")
        return {"success": True}
    return result

def create_payment_link(booking_ref):
    """Step 4: Create payment link - FIXED - NO HARDCODING"""
    print("💳 STEP 4: Creating payment link...")
    payload = {
        "bookingRef": booking_ref,
        "action": "quote",
        "postPaymentUrl": "https://wasteking.co.uk/thank-you/"
    }
    result = wasteking_request("api/booking/update", payload)
    
    if result.get('success'):
        # Check for payment link in response
        payment_link = None
        quote_data = result.get('quote', {})
        
        # Try different possible field names for payment link
        payment_link = (result.get('paymentLink') or 
                       result.get('payment_link') or 
                       result.get('quoteUrl') or
                       quote_data.get('paymentLink') or
                       quote_data.get('payment_link'))
        
        if payment_link:
            print(f"✅ PAYMENT LINK CREATED: {payment_link}")
            return {"success": True, "payment_link": payment_link}
        else:
            print(f"❌ Payment link not found in response: {result}")
            return {"success": False, "error": "Payment link not found in API response"}
    else:
        print(f"❌ Payment link creation failed: {result}")
        return result

def complete_booking(customer_data):
    """Complete 4-step booking process - NO HARDCODING"""
    print("🚀 STARTING COMPLETE BOOKING PROCESS - NO HARDCODED VALUES...")
    
    # Validate required data - NO DEFAULTS
    required_fields = ['firstName', 'phone', 'postcode', 'service']
    for field in required_fields:
        if not customer_data.get(field):
            return {"success": False, "error": f"Missing required field: {field}"}
    
    # Step 1: Create booking
    booking_result = create_booking()
    if not booking_result.get('success'):
        return booking_result
    
    booking_ref = booking_result['booking_ref']
    
    # Step 2: Get pricing - REAL API PRICES ONLY
    pricing_result = get_pricing(
        booking_ref, 
        customer_data['postcode'], 
        customer_data['service'],
        customer_data.get('type')  # Include type if provided
    )
    if not pricing_result.get('success'):
        return pricing_result
    
    price = pricing_result['price']
    
    # Step 3: Update details
    details_result = update_booking_details(booking_ref, customer_data)
    if not details_result.get('success'):
        return details_result
    
    # Step 4: Create payment link - FIXED
    payment_result = create_payment_link(booking_ref)
    if not payment_result.get('success'):
        return payment_result
    
    payment_link = payment_result['payment_link']
    
    # Step 5: Send SMS if phone provided
    sms_sent = False
    if customer_data.get('phone') and payment_link:
        sms_sent = send_sms(customer_data, booking_ref, price, payment_link)
    
    return {
        "success": True,
        "booking_ref": booking_ref,
        "price": price,
        "payment_link": payment_link,
        "sms_sent": sms_sent
    }

def send_sms(customer_data, booking_ref, price, payment_link):
    """Send SMS with payment link using Twilio - NO HARDCODING"""
    try:
        import os
        
        # Check Twilio credentials
        twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        twilio_token = os.getenv('TWILIO_AUTH_TOKEN') 
        twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        
        if not all([twilio_sid, twilio_token, twilio_phone]):
            print("⚠️ Twilio not configured - SMS not sent")
            return False
        
        try:
            from twilio.rest import Client
            client = Client(twilio_sid, twilio_token)
            
            phone = customer_data.get('phone', '')
            name = customer_data.get('firstName', 'Customer')
            
            # Format phone number
            if phone.startswith('0'):
                phone = f"+44{phone[1:]}"
            elif not phone.startswith('+'):
                phone = f"+44{phone}"
            
            message = f"Hi {name}, your booking confirmed! Ref: {booking_ref}, Price: {price}. Pay here: {payment_link}"
            
            result = client.messages.create(
                body=message,
                from_=twilio_phone,
                to=phone
            )
            
            print(f"✅ SMS sent to {phone} - SID: {result.sid}")
            return True
            
        except ImportError:
            print("❌ Twilio library not installed")
            return False
        except Exception as e:
            print(f"❌ SMS error: {e}")
            return False
            
    except Exception as e:
        print(f"❌ SMS setup error: {e}")
        return False

def is_business_hours():
    """Check if it's business hours - NO HARDCODING"""
    now = datetime.now()
    day_of_week = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour
    
    if day_of_week < 4:  # Monday-Thursday
        return 8 <= hour < 17
    elif day_of_week == 4:  # Friday
        return 8 <= hour < 16
    elif day_of_week == 5:  # Saturday
        return 9 <= hour < 12
    return False  # Sunday closed
