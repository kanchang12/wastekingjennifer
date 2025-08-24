import os
import requests
import json
from datetime import datetime

# WasteKing API Configuration
BASE_URL = os.getenv('WASTEKING_BASE_URL', 'https://wk-smp-api-dev.azurewebsites.net')
ACCESS_TOKEN = os.getenv('WASTEKING_ACCESS_TOKEN', 'wk-KZPY-tGF-@d.Aby9fpvMC_VVWkX-GN.i7jCBhF3xceoFfhmawaNc.RH.G_-kwk8*')

def wasteking_request(endpoint, payload, method="POST"):
    """Simple WasteKing API request function"""
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
        
        if response.status_code == 200:
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
    """Step 1: Create booking reference"""
    print("📋 STEP 1: Creating booking...")
    payload = {"type": "chatbot", "source": "wasteking.co.uk"}
    result = wasteking_request("api/booking/create", payload)
    
    if result.get('success'):
        booking_ref = result.get('bookingRef') or result.get('booking_ref')
        print(f"✅ BOOKING REF: {booking_ref}")
        return {"success": True, "booking_ref": booking_ref}
    return result

def get_pricing(booking_ref, postcode, service, skip_type="8yd"):
    """Step 2: Get pricing with booking ref - Extract REAL prices from API for specific postcode"""
    print(f"💰 STEP 2: Getting price for {service} {skip_type} at {postcode}...")
    payload = {
        "bookingRef": booking_ref,
        "search": {
            "postCode": postcode,
            "service": service
        }
    }
    result = wasteking_request("api/booking/update", payload)
    
    if result.get('success'):
        # Extract price from resultItems array for THIS specific postcode
        result_items = result.get('resultItems', [])
        
        print(f"🔍 API returned {len(result_items)} price options for {postcode}:")
        for item in result_items:
            print(f"   {item.get('type')}: {item.get('price')}")
        
        # Find the exact skip type requested
        for item in result_items:
            if item.get('type') == skip_type:
                price = item.get('price')
                if price and price != 'call' and price != '£0.00':
                    print(f"✅ FOUND {skip_type} for {postcode}: {price}")
                    return {"success": True, "price": price, "type": skip_type}
        
        # If exact type not available, get first available priced item
        for item in result_items:
            price = item.get('price')
            item_type = item.get('type')
            if price and price != 'call' and price != '£0.00':
                print(f"✅ FOUND {item_type} for {postcode}: {price}")
                return {"success": True, "price": price, "type": item_type}
        
        print(f"❌ No fixed prices available for {postcode} - all require phone quote")
        return {"success": False, "error": f"No fixed prices for {postcode}"}
    
    print(f"❌ API failed for {postcode}")
    return {"success": False, "error": "API call failed"}

def update_booking_details(booking_ref, customer_data):
    """Step 3: Update booking with customer details"""
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
    """Step 4: Create payment link"""
    print("💳 STEP 4: Creating payment link...")
    payload = {
        "bookingRef": booking_ref,
        "action": "quote",
        "postPaymentUrl": "https://wasteking.co.uk/thank-you/"
    }
    result = wasteking_request("api/booking/update", payload)
    
    if result.get('success'):
        payment_link = result.get('paymentUrl') or result.get('payment_link') or result.get('quoteUrl')
        print(f"✅ PAYMENT LINK: {payment_link}")
        return {"success": True, "payment_link": payment_link}
    return result

def complete_booking(customer_data):
    """Complete 4-step booking process with SMS"""
    print("🚀 STARTING COMPLETE BOOKING PROCESS...")
    
    # Step 1: Create booking
    booking_result = create_booking()
    if not booking_result.get('success'):
        return booking_result
    
    booking_ref = booking_result['booking_ref']
    
    # Step 2: Get pricing
    pricing_result = get_pricing(booking_ref, customer_data['postcode'], customer_data['service'])
    if not pricing_result.get('success'):
        return pricing_result
    
    price = pricing_result['price']
    
    # Step 3: Update details
    details_result = update_booking_details(booking_ref, customer_data)
    if not details_result.get('success'):
        return details_result
    
    # Step 4: Create payment link
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
    """Send SMS with payment link using Twilio"""
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
    """Check if it's business hours"""
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
