import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking, is_business_hours


class BaseAgent:
    def __init__(self, rules_processor):
        self.rules = rules_processor
        self.conversations = {}  # Store conversation state

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

    def has_required_data(self, state):
        required = ['firstName', 'phone', 'postcode', 'service']
        missing = [field for field in required if not state.get(field)]
        if missing:
            print(f"❌ MISSING REQUIRED DATA: {missing}")
            return False
        return True

    def should_get_price(self, message, state):
        price_words = ['price', 'cost', 'quote', 'how much', 'availability']
        return any(word in message.lower() for word in price_words)

    def should_book(self, message):
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'alright', 'sure', 'lets do it', 'go ahead']
        return any(word in message.lower() for word in positive_words)

    def send_forward_notification(self, manager_phone, state, service_type, price):
        try:
            twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
            twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
            twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
            if twilio_sid and twilio_token and twilio_phone:
                from twilio.rest import Client
                client = Client(twilio_sid, twilio_token)
                customer_name = state.get('firstName', 'Customer')
                customer_phone = state.get('phone', 'Unknown')
                postcode = state.get('postcode', 'Unknown')
                message = f"FORWARD: {service_type} booking £{price} for {customer_name} ({customer_phone}) at {postcode}. Customer waiting for callback."
                client.messages.create(body=message, from_=twilio_phone, to=manager_phone)
                print(f"✅ Forward notification sent to {manager_phone}")
        except Exception as e:
            print(f"❌ Forward notification error: {e}")

    def send_sms(self, name, phone, booking_ref, price, payment_link):
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

    def complete_booking(self, state):
        try:
            result = complete_booking(state)
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}"
                if payment_link:
                    response += f". Payment link: {payment_link}"
                    if state.get('phone'):
                        self.send_sms(state['firstName'], state['phone'], booking_ref, price, payment_link)
                state['booking_completed'] = True
                return response
            else:
                return "Unable to complete booking. Our team will call you back."
        except Exception as e:
            print(f"❌ Booking error: {e}")
            return "Booking issue. Our team will contact you."


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
                data['type'] = '8yd'
        return data

    def get_next_response(self, message, state, conversation_id):
        # Get pricing
        answer = self.get_pricing(self, state, conversation_id)
    
        # If user says yes, complete booking
        if message.lower() in ['yes', 'y', 'yeah', 'ok', 'alright', 'sure', 'go ahead']:
            return self.complete_booking(state)
    
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
            return f"💰 {answer}. Would you like to book this?"



    def get_pricing(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            price_num = float(str(price_result['price']).replace('£', '').replace(',', ''))
            if price_num > 0:
                state['price'] = price_result['price']
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
        
                # This line sends the message to the user
                return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."
        except Exception as e:
            print(e)



class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        if any(size in message_lower for size in ['8-yard', '8 yard', '8yd']):
            data['type'] = '8yd'
        elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']):
            data['type'] = '6yd'
        elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']):
            data['type'] = '4yd'
        else:
            data['type'] = '4yd'  # Default
        return data

 
    def get_next_response(self, message, state, conversation_id):
        # Get pricing
        answer = self.get_pricing(self, state, conversation_id)
    
        # If user says yes, complete booking
        if message.lower() in ['yes', 'y', 'yeah', 'ok', 'alright', 'sure', 'go ahead']:
            return self.complete_booking(state)
    
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
            return f"💰 {answer}. Would you like to book this?"




    def get_pricing(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', '4yd')
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            price_num = float(str(price_result['price']).replace('£', '').replace(',', ''))
            if price_num > 0:
                state['price'] = price_result['price']
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
        
                # This line sends the message to the user
                return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."
        except Exception as e:
            print(e)

    def complete_booking(self, state):
        try:
            result = complete_booking(state)
            if result.get('success'):
                return f"✅ MAV booking confirmed! Ref: {result['booking_ref']}, Price: {result['price']}. Payment: {result.get('payment_link')}"
            else:
                return "Unable to complete booking. Our team will call you."
        except Exception as e:
            return "Booking issue. Our team will contact you."


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()
        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'
            if any(size in message_lower for size in ['8-tonne', '8 tonne', '8t']):
                data['type'] = '8t'
            elif any(size in message_lower for size in ['6-tonne', '6 tonne', '6t']):
                data['type'] = '6t'
            else:
                data['type'] = '6t'
        return data
        
    def get_next_response(self, message, state, conversation_id):
        # Get pricing
        answer = self.get_pricing(self, state, conversation_id)
    
        # If user says yes, complete booking
        if message.lower() in ['yes', 'y', 'yeah', 'ok', 'alright', 'sure', 'go ahead']:
            return self.complete_booking(state)
    
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
            return f"💰 {answer}. Would you like to book this?"


    
    def get_pricing(self, state, conversation_id):
        try:
            from utils.wasteking_api import create_booking, get_pricing
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6t')
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            price_num = float(str(price_result['price']).replace('£', '').replace(',', ''))
            if price_num > 0:
                state['price'] = price_result['price']
                state['type'] = price_result.get('type', skip_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
        
                # This line sends the message to the user
                return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return "Unable to get pricing for your area."
        except Exception as e:
            print(e)

    def complete_booking(self, state):
        try:
            result = complete_booking(state)
            if result.get('success'):
                return f"✅ Grab booking confirmed! Ref: {result['booking_ref']}, Price: {result['price']}. Payment: {result.get('payment_link')}"
            else:
                return "Unable to complete booking. Our team will call you."
        except Exception as e:
            return "Booking issue. Our team will contact you."

