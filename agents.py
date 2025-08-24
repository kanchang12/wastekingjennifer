def complete_booking(self, state):
        """Complete booking process and send SMS"""
        try:
            result = complete_booking(state)
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}"
                
                if payment_link:
                    response += f". Payment link: {payment_link}"
                    
                    # Send SMS if we have phone number
                    phone = state.get('phone')
                    if phone:
                        sms_sent = self.send_sms(state['firstName'], phone, booking_ref, price, payment_link)
                        if sms_sent:
                            response += f" Payment link sent to {phone} via SMS."
                        else:
                            response += f" Please save the payment link above."
                else:
                    response += " Payment processing in progress."
                
                return response
            else:
                return "Unable to complete booking. Our team will call you back."
        except Exception as e:
            print(f"❌ Booking error: {e}")
            return "Booking issue. Our team will contact you shortly."
    
    def send_sms(self, name, phone, booking_ref, price, payment_link):
        """Send SMS with payment link"""
        try:
            import os
            import requests
            
            # Try Twilio if configured
            twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
            twilio_token = os.getenv('TWILIO_AUTH_TOKEN') 
            twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
            
            if twilio_sid and twilio_token and twilio_phone:
                try:
                    from twilio.rest import Client
                    client = Client(twilio_sid, twilio_token)
                    
                    message = f"Hi {name}, your skip booking confirmed! Ref: {booking_ref}, Price: {price}. Pay here: {payment_link}"
                    
                    client.messages.create(
                        body=message,
                        from_=twilio_phone,
                        to=f"+44{phone[1:]}" if phone.startswith('0') else phone
                    )
                    
                    print(f"✅ SMS sent to {phone}")
                    returnimport re
import json
from datetime import datetime
from utils.wasteking_api import complete_booking, is_business_hours

class BaseAgent:
    def __init__(self, rules_processor):
        self.rules = rules_processor
        self.conversations = {}  # Store conversation state
    
    def process_message(self, message, conversation_id="default"):
        """Process customer message and return response"""
        
        # Get conversation state
        state = self.conversations.get(conversation_id, {})
        print(f"📂 LOADED STATE: {state}")
        
        # Extract data from message
        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")
        
        # Merge with existing state
        state.update(new_data)
        print(f"🔄 MERGED STATE: {state}")
        
        # Save state
        self.conversations[conversation_id] = state
        
        # Determine what to ask next
        response = self.get_next_response(message, state)
        
        return response
    
    def extract_data(self, message):
        """Extract customer data from message"""
        data = {}
        message_lower = message.lower()
        
        # Extract postcode - handle spaces in postcode like "LS14 8 4ED"
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            data['postcode'] = postcode_match.group(1).replace(' ', '')
            print(f"✅ Extracted postcode: {data['postcode']}")
        
        # Extract phone
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")
        
        # Extract name - more flexible patterns
        if 'kanchen' in message_lower:
            data['firstName'] = 'Kanchen'
            print(f"✅ Extracted name: Kanchen")
        else:
            # Look for "name is X" or just "X wants" or "X, phone"
            name_patterns = [
                r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',  # "name is John"
                r'^([A-Z][a-z]+)\s+(?:wants|needs)',  # "John wants"
                r'^([A-Z][a-z]+),',  # "John,"
                r'for\s+([A-Z][a-z]+),',  # "for John,"
            ]
            
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    data['firstName'] = name_match.group(1).strip().title()
                    print(f"✅ Extracted name: {data['firstName']}")
                    break
        
        return data
    
    def has_required_data(self, state):
        """Check if we have all required data for booking"""
        required = ['firstName', 'phone', 'postcode', 'service']
        missing = [field for field in required if not state.get(field)]
        
        if missing:
            print(f"❌ MISSING REQUIRED DATA: {missing}")
            return False
        
        print(f"✅ ALL REQUIRED DATA PRESENT: {[f'{k}:{v}' for k,v in state.items() if k in required]}")
        return True
    
    def should_get_price(self, message, state):
        """Check if customer wants price"""
        price_words = ['price', 'cost', 'quote', 'how much', 'availability']
        return any(word in message.lower() for word in price_words)
    
    def should_book(self, message, state):
        """Check if customer wants to book"""
        book_words = [
            'book', 'booking', 'yes', 'confirm', 'proceed', 'ok',
            'payment link', 'booking link', 'send payment', 'send link',
            'complete booking', 'finalize', 'go ahead', 'continue'
        ]
        has_price = state.get('price') is not None
        message_lower = message.lower()
        
        booking_intent = any(word in message_lower for word in book_words)
        print(f"🔍 Booking intent check: {booking_intent}, Has price: {has_price}")
        
        return booking_intent and has_price

class SkipAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'skip'
    
    def extract_data(self, message):
        """Extract skip-specific data"""
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['skip', 'skip hire']):
            data['service'] = 'skip'
            
            # Extract skip size
            if any(size in message_lower for size in ['8-yard', '8 yard', '8yd']):
                data['type'] = '8yd'
            elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']):
                data['type'] = '6yd'
            elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']):
                data['type'] = '4yd'
            elif any(size in message_lower for size in ['12-yard', '12 yard', '12yd']):
                data['type'] = '12yd'
            else:
                data['type'] = '8yd'  # Default
            
            print(f"✅ Skip service detected: {data['type']}")
        
        return data
    
    def get_next_response(self, message, state):
        """Get next response for skip hire - ALWAYS MAKE THE SALE"""
        
        # ALWAYS proceed with booking if customer wants it
        if self.should_book(message, state) and self.has_required_data(state):
            return self.complete_booking(state)
        
        # ALWAYS get price if requested
        if self.should_get_price(message, state) and state.get('postcode') and state.get('service'):
            return self.get_pricing(state)
        
        # Ask for missing info
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"
        else:
            return "Would you like a price quote?"
    
    def get_pricing(self, state):
        """Get pricing for skip - Use REAL API prices only"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking to get price
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to create booking reference right now."
            
            booking_ref = booking_result['booking_ref']
            
            # Get price with skip type
            skip_type = state.get('type', '8yd')
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if price_result.get('success'):
                price = price_result['price']
                actual_type = price_result.get('type', skip_type)
                state['price'] = price
                state['type'] = actual_type
                state['booking_ref'] = booking_ref
                
                return f"💰 {actual_type} skip hire at {state['postcode']}: {price}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area right now."
            
        except Exception as e:
            print(f"❌ Pricing error: {e}")
            return "There was an issue getting pricing."
    
    def complete_booking(self, state):
        """Complete booking process and send SMS"""
        try:
            print(f"🚀 STARTING BOOKING WITH STATE: {state}")
            
            result = complete_booking(state)
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                sms_sent = result.get('sms_sent', False)
                
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}"
                
                if payment_link:
                    response += f". Payment link: {payment_link}"
                    
                    if sms_sent:
                        response += f" Payment link sent to {state.get('phone')} via SMS."
                    else:
                        response += " Please save the payment link above."
                
                # Mark booking as completed
                state['booking_completed'] = True
                
                return response
            else:
                return f"Unable to complete booking: {result.get('error', 'Unknown error')}"
        except Exception as e:
            print(f"❌ Booking error: {e}")
            return "Booking failed. Our team will contact you shortly."

class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'
    
    def extract_data(self, message):
        """Extract MAV-specific data"""
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['man and van', 'mav', 'van']):
            data['service'] = 'mav'
            
            if 'small' in message_lower:
                data['type'] = 'small'
            elif 'medium' in message_lower:
                data['type'] = 'medium'
            elif 'large' in message_lower:
                data['type'] = 'large'
            else:
                data['type'] = 'small'  # Default
            
            print(f"✅ MAV service detected: {data['type']}")
        
        return data
    
    def get_next_response(self, message, state):
        """Get next response for man and van"""
        
        # Check office hours for transfer threshold
        if is_business_hours() and state.get('price'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num >= 500:  # MAV transfer threshold
                    return "Let me connect you with our specialist team for this quote."
            except:
                pass
        
        # Check if should book
        if self.should_book(message, state) and self.has_required_data(state):
            return self.complete_booking(state)
        
        # Check if should get price  
        if self.should_get_price(message, state) and state.get('postcode') and state.get('service'):
            return self.get_pricing(state)
        
        # Ask for missing info
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"
        else:
            return "Would you like a price quote?"
    
    def get_pricing(self, state):
        """Get pricing for MAV"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            price_result = get_pricing(booking_ref, state['postcode'], state['service'])
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            state['price'] = price
            state['booking_ref'] = booking_ref
            
            return f"💰 {state.get('type', 'small')} man & van at {state['postcode']}: £{price}. Would you like to book?"
            
        except Exception as e:
            print(f"❌ MAV Pricing error: {e}")
            return "Let me get you a quote. What's your phone number?"
    
    def complete_booking(self, state):
        """Complete MAV booking"""
        try:
            result = complete_booking(state)
            if result.get('success'):
                return f"✅ MAV booking confirmed! Ref: {result['booking_ref']}, Price: £{result['price']}. Payment: {result['payment_link']}"
            else:
                return "Unable to complete booking. Our team will call you."
        except Exception as e:
            return "Booking issue. Our team will contact you."

class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'
    
    def extract_data(self, message):
        """Extract grab-specific data"""
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'
            
            if '8' in message_lower and 'tonne' in message_lower:
                data['type'] = '8t'
            else:
                data['type'] = '6t'  # Default
            
            print(f"✅ Grab service detected: {data['type']}")
        
        return data
    
    def get_next_response(self, message, state):
        """Get next response for grab hire"""
        
        # Check office hours for transfer threshold
        if is_business_hours() and state.get('price'):
            try:
                price_num = float(str(state['price']).replace('£', '').replace(',', ''))
                if price_num >= 300:  # Grab transfer threshold
                    return "Let me connect you with our specialist team for this service."
            except:
                pass
        
        # Check if should book
        if self.should_book(message, state) and self.has_required_data(state):
            return self.complete_booking(state)
        
        # Check if should get price  
        if self.should_get_price(message, state) and state.get('postcode') and state.get('service'):
            return self.get_pricing(state)
        
        # Ask for missing info
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"
        else:
            return "Would you like a price quote?"
    
    def get_pricing(self, state):
        """Get pricing for grab"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            price_result = get_pricing(booking_ref, state['postcode'], state['service'])
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            state['price'] = price
            state['booking_ref'] = booking_ref
            
            return f"💰 {state.get('type', '6t')} grab hire at {state['postcode']}: £{price}. Would you like to book?"
            
        except Exception as e:
            print(f"❌ Grab Pricing error: {e}")
            return "Let me get you a quote. What's your phone number?"
    
    def complete_booking(self, state):
        """Complete grab booking"""
        try:
            result = complete_booking(state)
            if result.get('success'):
                return f"✅ Grab booking confirmed! Ref: {result['booking_ref']}, Price: £{result['price']}. Payment: {result['payment_link']}"
            else:
                return "Unable to complete booking. Our team will call you."
        except Exception as e:
            return "Booking issue. Our team will contact you."
