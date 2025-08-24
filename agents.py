import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking


class BaseAgent:
    def __init__(self, rules_processor):
        self.rules = rules_processor
        self.conversations = {}  # Store conversation state
        
        # Configurable rules list - can be updated without code changes
        self.rules_list = [
            # "I will write new rules",
            # "now it will be blank",
            # "then what ever will come I will add",
            # "so that I dont need to change the code again"
        ]

    def process_message(self, message, conversation_id="default"):
        state = self.conversations.get(conversation_id, {})
        print(f"📂 LOADED STATE: {state}")

        new_data = self.extract_data(message)
        print(f"🔍 NEW DATA: {new_data}")

        state.update(new_data)
        print(f"🔄 MERGED STATE: {state}")

        self.conversations[conversation_id] = state

        response = self.get_next_response(message, state, conversation_id)
        return response

    def extract_data(self, message):
        data = {}
        message_lower = message.lower()

        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            data['postcode'] = postcode_match.group(1).replace(' ', '')
            print(f"✅ Extracted postcode: {data['postcode']}")

        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")

        if 'kanchen' in message_lower:
            data['firstName'] = 'Kanchen'
            print(f"✅ Extracted name: Kanchen")
        else:
            name_patterns = [
                r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                r'^([A-Z][a-z]+)\s+(?:wants|needs)',
                r'^([A-Z][a-z]+),',
                r'for\s+([A-Z][a-z]+),',
            ]
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    data['firstName'] = name_match.group(1).strip().title()
                    print(f"✅ Extracted name: {data['firstName']}")
                    break
        return data

    def should_book(self, message):
        """Check if user wants to proceed with booking"""
        message_lower = message.lower()
        
        booking_phrases = [
            'payment link', 'pay link', 'booking', 'book it', 'book this',
            'send payment', 'complete booking', 'finish booking', 'proceed with booking',
            'confirm booking', 'make booking', 'create booking', 'place order',
            'send me the link', 'i want to book', 'ready to book', 'lets book',
            'checkout', 'complete order', 'finalize booking', 'secure booking',
            'reserve this', 'confirm this', 'i\'ll take it', 'that works',
            'perfect', 'sounds good', 'thats fine', 'arrange this'
        ]
        
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure', 'lets do it', 'go ahead', 'proceed']
        
        if any(phrase in message_lower for phrase in booking_phrases):
            return True
            
        return any(word in message_lower for word in positive_words)

    def should_get_price(self, message):
        """Check if user wants pricing"""
        price_words = ['price', 'cost', 'quote', 'how much', 'availability', 'pricing']
        return any(word in message.lower() for word in price_words)

    def is_business_hours(self):
        """Check business hours - ONLY for transfer decisions"""
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

    def needs_transfer(self, price):
        """
        CRITICAL RULE: ONLY check business hours when transfer would be needed
        - Regular operations = NEVER check time
        - Transfer needed = CHECK time, if out of hours = DON'T TRANSFER, MAKE THE SALE
        """
        if self.service_type == 'skip':
            return False  # Skip has NO_LIMIT - never transfer
        
        elif self.service_type == 'mav' and price >= 500:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - TRANSFER WOULD BE NEEDED BUT OUT OF HOURS = MAKE THE SALE INSTEAD")
                return False  # Don't transfer, handle the sale
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £500+ MAV")
            return True  # Transfer to specialist
            
        elif self.service_type == 'grab' and price >= 300:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - TRANSFER WOULD BE NEEDED BUT OUT OF HOURS = MAKE THE SALE INSTEAD")
                return False  # Don't transfer, handle the sale
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £300+ GRAB")
            return True  # Transfer to specialist
            
        return False

    def complete_booking_proper(self, state):
        """Complete booking with payment link - THE 5 STEPS"""
        try:
            print("🚀 COMPLETING BOOKING...")
            
            # Prepare customer data
            customer_data = {
                'firstName': state.get('firstName'),
                'phone': state.get('phone'),
                'postcode': state.get('postcode'),
                'service': state.get('service'),
                'type': state.get('type')
            }
            
            print(f"📋 CUSTOMER DATA: {customer_data}")
            
            # Call the complete booking API
            result = complete_booking(customer_data)
            
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                print(f"✅ BOOKING SUCCESS: {booking_ref}, {price}")
                
                # Update state with REQUIRED date and time
                current_datetime = datetime.now()
                state['booking_completed'] = True
                state['booking_ref'] = booking_ref
                state['final_price'] = price
                state['booking_date'] = current_datetime.strftime('%Y%m%d')  # 20250824 format
                state['booking_time'] = current_datetime.strftime('%I:%M %p')  # 12:30 PM format
                
                # Send SMS if phone provided
                if payment_link and state.get('phone'):
                    self.send_sms(state['firstName'], state['phone'], booking_ref, price, payment_link)
                
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}"
                if payment_link:
                    response += f"\n💳 Payment link sent to your phone: {payment_link}"
                
                return response
            else:
                print(f"❌ BOOKING FAILED: {result}")
                return "Unable to complete booking. Our team will call you back."
                
        except Exception as e:
            print(f"❌ BOOKING ERROR: {e}")
            return "Booking issue occurred. Our team will contact you."

    def send_sms(self, name, phone, booking_ref, price, payment_link):
        """Send SMS with payment link"""
        try:
            twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
            twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
            twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
            
            if twilio_sid and twilio_token and twilio_phone:
                from twilio.rest import Client
                client = Client(twilio_sid, twilio_token)
                
                formatted_phone = f"+44{phone[1:]}" if phone.startswith('0') else phone
                message = f"Hi {name}, your booking confirmed! Ref: {booking_ref}, Price: {price}. Pay here: {payment_link}"
                
                client.messages.create(body=message, from_=twilio_phone, to=formatted_phone)
                print(f"✅ SMS sent to {phone}")
        except Exception as e:
            print(f"❌ SMS error: {e}")


class SkipAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'skip'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['skip', 'skip hire']):
            data['service'] = 'skip'
            
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
                
        return data

    def get_next_response(self, message, state, conversation_id):
        """ORIGINAL WORKING STRUCTURE"""
        wants_to_book = self.should_book(message)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)
        
        # Ask for missing required info first
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"
        
        # If user wants to book but we don't have price yet, get price and complete booking
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        # If we have all data but no price yet, get pricing
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # If we have pricing, ask to book
        elif state.get('price'):
            return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"
        
        return "How can I help you with skip hire?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # 1. First create booking ref
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            # 2. Second get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately
                return self.complete_booking_proper(state)
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # 1. First create booking ref
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            # 2. Second get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return "Unable to get pricing for your area."
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                # Update state
                state['price'] = price
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check if needs transfer (Skip has no limit, so no transfer needed)
                return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'

            if 'large' in message_lower:
                data['type'] = '8yd'
            elif 'medium' in message_lower:
                data['type'] = '6yd'
            elif 'small' in message_lower:
                data['type'] = '4yd'
            else:
                data['type'] = '4yd'  # Default

        return data

    def get_next_response(self, message, state, conversation_id):
        """ORIGINAL WORKING STRUCTURE"""
        wants_to_book = self.should_book(message)

        # PDF RULE: Heavy materials check for MAV - if bricks/mortar mentioned
        if any(mat in message.lower() for mat in ['bricks', 'mortar', 'soil', 'rubble', 'concrete', 'tiles']):
            if self.is_business_hours():
                return "For heavy materials with man & van service, let me put you through to our specialist team for the best solution."
            else:
                return "For heavy materials with man & van, I can take your details for our specialist team to call back."

        if wants_to_book and state.get('price') and state.get('booking_ref'):
            return self.complete_booking_proper(state)

        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"

        elif wants_to_book and not state.get('price'):
            return self.get_pricing_and_complete_booking(state, conversation_id)

        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)

        elif state.get('price'):
            return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with man & van service?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing

            # 1. First create booking ref
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', '4yd')

            # 2. Second get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                return self.complete_booking_proper(state)
            else:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing

            # 1. First create booking ref
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', '4yd')

            # 2. Second get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'

            if any(size in message_lower for size in ['8-tonne', '8 tonne', '8t', '16-tonne']):
                data['type'] = '8t'
            elif any(size in message_lower for size in ['6-tonne', '6 tonne', '6t', '12-tonne']):
                data['type'] = '6t'
            else:
                data['type'] = '6t'  # Default
        else:
            data['service'] = 'grab'
            data['type'] = '6t'

        return data

    def get_next_response(self, message, state, conversation_id):
        wants_to_book = self.should_book(message)

        if wants_to_book and state.get('price') and state.get('booking_ref'):
            return self.complete_booking_proper(state)

        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your postcode?"
        elif not state.get('phone'):
            return "What's your phone number?"
        elif not state.get('service'):
            return "What service do you need?"

        elif wants_to_book and not state.get('price'):
            return self.get_pricing_and_complete_booking(state, conversation_id)

        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)

        elif state.get('price'):
            return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with grab hire?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing

            # 1. First create booking ref
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6t')

            # 2. Second get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                return self.complete_booking_proper(state)
            else:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."

    def get_pricing_and_ask(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing

            # 1. First create booking ref
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6t')

            # 2. Second get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            if not price_result.get('success'):
                return "Unable to get pricing for your area."

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now."
