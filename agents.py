import re
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
        
        # Extract data from message
        new_data = self.extract_data(message)
        state.update(new_data)
        
        # Save state
        self.conversations[conversation_id] = state
        
        # Determine what to ask next
        response = self.get_next_response(message, state)
        
        return response
    
    def extract_data(self, message):
        """Extract customer data from message"""
        data = {}
        message_lower = message.lower()
        
        # Extract postcode
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})', message.upper())
        if postcode_match:
            data['postcode'] = postcode_match.group(1).replace(' ', '')
            print(f"✅ Extracted postcode: {data['postcode']}")
        
        # Extract phone
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")
        
        # Extract name
        if 'kanchen ghosh' in message_lower:
            data['firstName'] = 'Kanchen Ghosh'
        else:
            name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message)
            if name_match:
                data['firstName'] = name_match.group(1).strip().title()
                print(f"✅ Extracted name: {data['firstName']}")
        
        return data
    
    def has_required_data(self, state):
        """Check if we have all required data"""
        required = ['firstName', 'phone', 'postcode', 'service']
        return all(state.get(field) for field in required)
    
    def should_get_price(self, message, state):
        """Check if customer wants price"""
        price_words = ['price', 'cost', 'quote', 'how much', 'availability']
        return any(word in message.lower() for word in price_words)
    
    def should_book(self, message, state):
        """Check if customer wants to book"""
        book_words = ['book', 'yes', 'confirm', 'proceed', 'ok']
        has_price = state.get('price') is not None
        return any(word in message.lower() for word in book_words) and has_price

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
        """Get next response for skip hire"""
        
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
        """Get pricing for skip"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking to get price
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now. Can I take your details?"
            
            booking_ref = booking_result['booking_ref']
            
            # Get price
            price_result = get_pricing(booking_ref, state['postcode'], state['service'])
            if not price_result.get('success'):
                return "Unable to get pricing for your area. Can I take your details?"
            
            price = price_result['price']
            state['price'] = price
            state['booking_ref'] = booking_ref
            
            return f"💰 {state.get('type', '8yd')} skip hire at {state['postcode']}: £{price}. Would you like to book this?"
            
        except Exception as e:
            print(f"❌ Pricing error: {e}")
            return "Let me get you a quote. What's your phone number?"
    
    def complete_booking(self, state):
        """Complete booking process"""
        try:
            result = complete_booking(state)
            if result.get('success'):
                return f"✅ Booking confirmed! Ref: {result['booking_ref']}, Price: £{result['price']}. Payment link: {result['payment_link']}"
            else:
                return "Unable to complete booking. Our team will call you back."
        except Exception as e:
            print(f"❌ Booking error: {e}")
            return "Booking issue. Our team will contact you shortly."

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
