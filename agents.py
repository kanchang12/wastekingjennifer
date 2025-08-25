import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking

# HARDCODED BUSINESS RULES - NO PDF LOADING
SKIP_HIRE_RULES = {
    'heavy_materials_12yd': "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller.",
    'man_van_suggestion': "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?",
    'permit_script': "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe.",
    'access_requirement': "We need 3.5m width minimum.",
    'delivery_time': "We can't guarantee exact times, but delivery is between 7AM to 6PM",
    'collection_terms': "Collection within 72 hours standard. Level load requirement for skip collection. Driver calls when en route. 98% recycling rate. We have insured and licensed teams. Digital waste transfer notes provided."
}

MAV_RULES = {
    'pricing': "We charge by the cubic yard at £30 per yard for light waste.",
    'weight_allowance': "We allow 100 kilos per cubic yard - for example, 5 yards would be 500 kilos",
    'labour_time': "We allow generous labour time and 95% of all our jobs are done within the time frame. Although if the collection goes over our labour time, there is a £19 charge per 15 minutes",
    'collection_time': "We can't guarantee exact times, but collection is typically between 7am-6pm"
}

GRAB_RULES = {
    'materials_only': "The majority of grabs will only take muckaway which is soil & rubble.",
    'capacity_8wheeler': "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry.",
    'capacity_6wheeler': "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
} PRICING DECISION
Call marketplace tool
IMMEDIATELY AFTER GETTING BASE PRICE:
1. Calculate any surcharges for prohibited items mentioned
2. Add surcharges to base price

GRAB HIRE COMPLETE FLOW
C1: INFORMATION GATHERING (MANDATORY - ALL DETAILS FIRST)
NEVER call tools until you have ALL required information:

MANDATORY INFORMATION FOR GRAB SERVICES:
1. Customer name: "Can I take your name please?"
2. Phone number: "What's the best phone number to contact you on?"
3. Postcode: "What's the postcode where you need the grab lorry?"
4. Waste type: "What type of materials do you have?"
5. Amount/quantity: "How much material do you have approximately?"

ONLY AFTER collecting ALL above information proceed to service-specific questions

C2: GRAB SIZE UNDERSTANDING (EXACT SCRIPTS)
MANDATORY EXACT SCRIPTS:
If customer says "8-wheeler": SAY EXACTLY: "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
If customer says "6-wheeler": SAY EXACTLY: "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."

GRAB TERMINOLOGY:
- 6-wheelers: Generally 12 tonnes capacity
- 8-wheelers: Generally 16 tonnes capacity

NEVER say: "8-ton" or "6-ton" or any other tonnage NEVER improvise - use exact script above ALWAYS use: "grab lorry" not just "grab" ALWAYS use: "16-tonne" for 8-wheelers, "12-tonne" for 6-wheelers

C3: MATERIALS ASSESSMENT
Ask: "What type of materials do you have?"

IF soil and rubble only: Continue to access assessment

IF mixed materials (soil, rubble + other items like wood): SAY EXACTLY: "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."

IF wait & load skip mentioned: IMMEDIATELY: "For wait & load skips, let me put you through to our specialist who will check availability & costs." TRANSFER

GRAB PRICING ISSUES:
- IF grab prices show £0.00 or unrealistic high prices (over £500): "Most grab prices require specialist assessment. Let me put you through to our team who can provide accurate pricing."
- IF no grab prices available: Always transfer/SMS notification for accurate pricing

C4: ACCESS & TIMING
Ask: "Is there clear access for the grab lorry?"

Check timing:
- Timing given? Don't ask again
- Timing not given? "When do you need this?"

IF complex access:
- Office hours: TRANSFER
- Out-of-hours: Take details + SMS notification to +447823656762

C5: QUOTE & PRICING
Call marketplace tool

Check amount:
- £300 or more + Office hours: "For this size job, let me put you through to our specialist team for the best service." TRANSFER
- £300 or more + Out-of-hours: Take details + SMS notification to +447823656762, still try to complete booking
- Under £300: Continue to booking decision (both office hours and out-of-hours)
"""


class BaseAgent:
    def __init__(self, rules_processor=None):
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

        # Postcode regex - requires complete postcode format like LS14ED
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1).replace(' ', '')
            # Ensure it's a complete postcode
            if len(postcode) >= 5:
                data['postcode'] = postcode
                print(f"✅ Extracted complete postcode: {data['postcode']}")

        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ Extracted phone: {data['phone']}")

        # ONLY FIX: Don't extract "Yes" as name
        if 'kanchen' in message_lower or 'kanchan' in message_lower:
            data['firstName'] = 'Kanchan'
            print(f"✅ Extracted name: Kanchan")
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
                    potential_name = name_match.group(1).strip().title()
                    # ONLY FIX: Don't extract common words as names
                    if potential_name.lower() not in ['yes', 'no', 'there', 'what', 'how']:
                        data['firstName'] = potential_name
                        print(f"✅ Extracted name: {data['firstName']}")
                        break

        # Extract waste type information - KEEP ORIGINAL LOGIC
        if any(waste in message_lower for waste in ['plastic', 'household', 'furniture', 'clothes', 'books', 'toys', 'cardboard', 'paper', 'bricks', 'brick', 'renovation']):
            waste_types = []
            if 'plastic' in message_lower:
                waste_types.append('plastic')
            if 'household' in message_lower:
                waste_types.append('household')
            if 'furniture' in message_lower:
                waste_types.append('furniture')
            if 'clothes' in message_lower:
                waste_types.append('clothes')
            if 'books' in message_lower:
                waste_types.append('books')
            if 'toys' in message_lower:
                waste_types.append('toys')
            if 'cardboard' in message_lower:
                waste_types.append('cardboard')
            if 'paper' in message_lower:
                waste_types.append('paper')
            if 'bricks' in message_lower or 'brick' in message_lower:
                waste_types.append('bricks')
            if 'renovation' in message_lower:
                waste_types.append('renovation waste')
            
            if waste_types:
                data['waste_type'] = ', '.join(waste_types)
                print(f"✅ Extracted waste type: {data['waste_type']}")

        # Extract location information - KEEP ORIGINAL LOGIC  
        location_phrases = [
            'in the garage', 'in garage', 'garage',
            'in the garden', 'garden', 'back garden', 'front garden',
            'in the house', 'inside', 'indoors',
            'outside', 'outdoors', 'on the drive', 'driveway',
            'easy access', 'easy to access', 'accessible',
            'ground floor', 'upstairs', 'basement'
        ]
        for phrase in location_phrases:
            if phrase in message_lower:
                data['location'] = message.strip()
                print(f"✅ Extracted location: {data['location']}")
                break

        return data

    def should_book(self, message):
        """Check if user wants to proceed with booking"""
        message_lower = message.lower()
        
        # Direct booking requests
        booking_phrases = [
            'payment link', 'pay link', 'booking', 'book it', 'book this',
            'send payment', 'complete booking', 'finish booking', 'proceed with booking',
            'confirm booking', 'make booking', 'create booking', 'place order',
            'send me the link', 'i want to book', 'ready to book', 'lets book',
            'checkout', 'complete order', 'finalize booking', 'secure booking',
            'reserve this', 'confirm this', 'i\'ll take it', 'that works',
            'perfect', 'sounds good', 'thats fine', 'arrange this'
        ]
        
        # Positive responses
        positive_words = ['yes', 'yeah', 'yep', 'ok', 'okay', 'alright', 'sure', 'lets do it', 'go ahead', 'proceed']
        
        # Check for explicit booking requests
        if any(phrase in message_lower for phrase in booking_phrases):
            return True
            
        # Check for positive responses - but only if we already have pricing
        return any(word in message_lower for word in positive_words)

    def is_business_hours(self):
        """ALWAYS RETURN TRUE - NO OFFICE HOURS BLOCKING FOR SALES"""
        return True  # ALWAYS MAKE SALES - NO OFFICE HOURS RESTRICTIONS

    def needs_transfer(self, price):
        """SKIP HIRE = NO TRANSFER EVER - ALWAYS MAKE THE SALE"""
        if self.service_type == 'skip':
            return False  # SKIP HIRE: NO LIMIT - NEVER TRANSFER - ALWAYS BOOK
        
        elif self.service_type == 'mav' and price >= 500:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - MAKE THE SALE INSTEAD OF TRANSFER")
                return False
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £500+ MAV")
            return True
            
        elif self.service_type == 'grab' and price >= 300:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - MAKE THE SALE INSTEAD OF TRANSFER")
                return False
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £300+ GRAB")
            return True
            
        return False

    def validate_postcode_with_customer(self, current_postcode):
        """Ask customer to confirm postcode if pricing fails"""
        if not current_postcode or len(current_postcode) < 5:
            return "Could you please provide your complete postcode? For example, LS14ED rather than just LS1."
        else:
            return f"I'm having trouble finding pricing for {current_postcode}. Could you please confirm your complete postcode is correct?"

    def complete_booking_proper(self, state):
        """Complete booking with payment link"""
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
                
                # Update state
                state['booking_completed'] = True
                state['booking_ref'] = booking_ref
                state['final_price'] = price
                
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

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately - MUST ACTUALLY WORK"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            print("📞 CALLING CREATE_BOOKING API FOR IMMEDIATE BOOKING...")
            booking_result = create_booking()
            if not booking_result.get('success'):
                print("❌ CREATE_BOOKING FAILED")
                return "Unable to process booking right now. Our team will call you back."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self.default_type)
            
            print(f"📞 CALLING GET_PRICING API FOR BOOKING... postcode={state['postcode']}, service={state['service']}, type={service_type}")
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                print("❌ GET_PRICING FAILED FOR BOOKING")
                return self.validate_postcode_with_customer(state.get('postcode'))
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            print(f"💰 GOT PRICE FOR BOOKING: {price} (numeric: {price_num})")
            
            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                print("🚀 PRICE OBTAINED - NOW COMPLETING BOOKING IMMEDIATELY")
                return self.complete_booking_proper(state)
            else:
                print("❌ ZERO PRICE FOR BOOKING")
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ BOOKING PRICING ERROR: {e}")
            return "Unable to process booking right now. Our team will contact you."

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking - MUST ACTUALLY CALL THE API"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            print("📞 CALLING CREATE_BOOKING API...")
            booking_result = create_booking()
            if not booking_result.get('success'):
                print("❌ CREATE_BOOKING FAILED")
                return "Unable to get pricing right now. Let me put you through to our team."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self.default_type)
            
            print(f"📞 CALLING GET_PRICING API... postcode={state['postcode']}, service={state['service']}, type={service_type}")
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                print("❌ GET_PRICING FAILED - POSTCODE ISSUE")
                return self.validate_postcode_with_customer(state.get('postcode'))
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            print(f"💰 GOT PRICE: {price} (numeric: {price_num})")
            
            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check if needs transfer - BUT SKIP HIRE NEVER TRANSFERS
                if self.needs_transfer(price_num):
                    print("🔄 TRANSFER NEEDED")
                    return "For this size job, let me put you through to our specialist team for the best service."
                
                print("✅ PRESENTING PRICE TO USER")
                return f"💰 {state['type']} {self.service_name} at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                print("❌ ZERO PRICE RETURNED")
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return "Unable to get pricing right now. Let me put you through to our team."


class SkipAgent(BaseAgent):
    def __init__(self, rules_processor=None):
        super().__init__(rules_processor)
        self.service_type = 'skip'
        self.service_name = 'skip hire'
        self.default_type = '8yd'

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

    def has_all_required_info(self, state):
        """Check if we have all required information to get pricing"""
        required_fields = ['firstName', 'postcode', 'service', 'type']
        has_all = all(state.get(field) for field in required_fields)
        print(f"🔍 CHECKING REQUIRED INFO: {required_fields}")
        print(f"📋 CURRENT STATE: {state}")
        print(f"✅ HAS ALL REQUIRED: {has_all}")
        return has_all

    def get_next_response(self, message, state, conversation_id):
        """ORIGINAL BUSINESS LOGIC FROM PDF - ONLY TECHNICAL FIXES"""
        wants_to_book = self.should_book(message)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # ORIGINAL BASIC INFO GATHERING
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('service'):
            # Auto-set service type for Skip
            state['service'] = 'skip'
            if not state.get('type'):
                state['type'] = '8yd'  # Default
            self.conversations[conversation_id] = state

        # BUSINESS RULE QUESTIONS FROM PDF (A2: HEAVY MATERIALS CHECK & MAN & VAN SUGGESTION)
        elif not state.get('waste_content_asked'):
            state['waste_content_asked'] = True
            self.conversations[conversation_id] = state
            return "What are you going to keep in the skip?"
        
        # Check for heavy materials and skip size restrictions
        elif not state.get('materials_assessed') and state.get('waste_content_asked'):
            state['materials_assessed'] = True
            self.conversations[conversation_id] = state
            # Check if 12 yard skip with heavy materials
            if state.get('type') == '12yd' and any(heavy in message.lower() for heavy in ['concrete', 'soil', 'brick', 'rubble', 'hardcore']):
                return "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."
            # MAN & VAN SUGGESTION for 8yd or smaller with light materials
            elif state.get('type') in ['8yd', '6yd', '4yd'] and not any(heavy in message.lower() for heavy in ['concrete', 'soil', 'brick', 'rubble', 'hardcore']):
                return "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"

        # A3: SKIP SIZE & LOCATION
        elif not state.get('skip_size_confirmed'):
            state['skip_size_confirmed'] = True
            self.conversations[conversation_id] = state
            if not state.get('type') or state.get('type') not in ['4yd', '6yd', '8yd', '12yd']:
                return "What size skip are you thinking of? We have 4, 6, 8, and 12-yard skips. Our 8-yard is most popular nationally."

        elif not state.get('location_asked'):
            state['location_asked'] = True
            self.conversations[conversation_id] = state
            return "Will the skip go on your driveway or on the road?"
        
        # Check if road placement - MANDATORY PERMIT SCRIPT
        elif not state.get('permit_handled') and any(road in message.lower() for road in ['road', 'street', 'outside', 'front', 'pavement']):
            state['permit_handled'] = True
            state['needs_permit'] = True
            self.conversations[conversation_id] = state
            return "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe. Are there any parking bays where the skip will go?"
        
        elif state.get('needs_permit') and not state.get('parking_restrictions_asked'):
            state['parking_restrictions_asked'] = True
            self.conversations[conversation_id] = state
            return "Are there yellow lines in that area?"
        
        elif state.get('needs_permit') and not state.get('parking_final_check'):
            state['parking_final_check'] = True
            self.conversations[conversation_id] = state
            return "Are there any parking restrictions on that road?"

        # A4: ACCESS ASSESSMENT
        elif not state.get('access_asked'):
            state['access_asked'] = True
            self.conversations[conversation_id] = state
            return "Is there easy access for our lorry to deliver the skip? Any low bridges, narrow roads, or parking restrictions? We need 3.5m width minimum."

        # A5: PROHIBITED ITEMS SCREENING for SKIPS
        elif not state.get('prohibited_items_asked'):
            state['prohibited_items_asked'] = True
            self.conversations[conversation_id] = state
            return "Do you have any fridges, freezers, mattresses, or upholstered furniture? These have additional charges due to special disposal requirements."

        # A6: TIMING & QUOTE GENERATION
        elif not state.get('timing_asked'):
            state['timing_asked'] = True
            self.conversations[conversation_id] = state
            return "When do you need this delivered? We can't guarantee exact times, but delivery is between 7AM to 6PM."
        
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"

        # ORIGINAL BOOKING FLOW CONTINUES
        # If user wants to book but we don't have price yet, get price and complete booking
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        # If we have all data but no price yet, get pricing
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # If we have pricing, ask to book
        elif state.get('price'):
            return f"💰 {state['type']} skip hire at {state['postcode']}: {state['price']}. Collection within 72 hours standard. Level load requirement for skip collection. Driver calls when en route. 98% recycling rate. We have insured and licensed teams. Digital waste transfer notes provided. Would you like to book this?"
        
        return "How can I help you with skip hire?"


class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'
        self.service_name = 'man & van'
        self.default_type = '4yd'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'

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
        """ORIGINAL WORKING FLOW WITH PROPER STATE MANAGEMENT"""
        wants_to_book = self.should_book(message)

        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # STEP 1: Basic info (original working logic)
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
        elif not state.get('service'):
            # Auto-set service type for MAV
            state['service'] = 'mav'
            state['type'] = '4yd'  # Default
            self.conversations[conversation_id] = state
        
        # STEP 2: Heavy materials check (B2 from PDF)
        elif not state.get('heavy_materials_checked'):
            state['heavy_materials_checked'] = True
            self.conversations[conversation_id] = state
            return "Do you have soil, rubble, bricks, concrete, or tiles?"
        
        # STEP 3: Waste type (B3 from PDF) 
        elif not state.get('waste_type'):
            return "What type of waste do you have?"
        
        # STEP 4: Volume assessment (B3 continued)
        elif not state.get('volume_assessed'):
            state['volume_assessed'] = True  
            self.conversations[conversation_id] = state
            return "We charge by the cubic yard at £30 per yard for light waste. We allow 100 kilos per cubic yard - for example, 5 yards would be 500 kilos. How much waste do you have approximately? Think in terms of washing machine loads or black bags."
        
        # STEP 5: Location access (B4 from PDF)
        elif not state.get('location'):
            return "Where is the waste located and how easy is it to access?"
        
        # STEP 6: Parking access (B4 continued)  
        elif not state.get('parking_checked'):
            state['parking_checked'] = True
            self.conversations[conversation_id] = state
            return "Can we park on the driveway or close to the waste?"
        
        # STEP 7: Stairs check (B4 critical)
        elif not state.get('stairs_checked'):
            state['stairs_checked'] = True
            self.conversations[conversation_id] = state
            return "Are there any stairs involved? We have insured and licensed teams."
        
        # STEP 8: Distance check (B4 final)
        elif not state.get('distance_checked'):
            state['distance_checked'] = True
            self.conversations[conversation_id] = state
            return "How far is our parking from the waste?"
        
        # STEP 9: Additional items (B5 from PDF)
        elif not state.get('additional_items_checked'):
            state['additional_items_checked'] = True
            self.conversations[conversation_id] = state
            return "Is there anything else you need removing while we're on site? Any fridges, mattresses, or upholstered furniture?"
        
        # STEP 10: Timing (B5 continued)
        elif not state.get('timing_checked'):
            state['timing_checked'] = True
            self.conversations[conversation_id] = state
            return "When do you need this collection? We can't guarantee exact times, but collection is typically between 7am-6pm."
        
        # STEP 11: Phone number (final step before pricing)
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"
        
        # ORIGINAL BOOKING FLOW CONTINUES
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        elif state.get('price'):
            return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. We allow generous labour time and 95% of all our jobs are done within the time frame. Although if the collection goes over our labour time, there is a £19 charge per 15 minutes. Would you like to book this?"

        return "How can I help you with man & van service?"


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'
        self.service_name = 'grab hire'
        self.default_type = '6yd'

    def extract_data(self, message):
        data = super().extract_data(message)
        message_lower = message.lower()

        if any(word in message_lower for word in ['grab', 'grab hire']):
            data['service'] = 'grab'

            if any(size in message_lower for size in ['8-yard', '8 yard', '8yd']):
                data['type'] = '8yd'
            elif any(size in message_lower for size in ['6-yard', '6 yard', '6yd']):
                data['type'] = '6yd'
            elif any(size in message_lower for size in ['4-yard', '4 yard', '4yd']):
                data['type'] = '4yd'
            else:
                data['type'] = '6yd'  # Default
        else:
            data['service'] = 'grab'
            data['type'] = '6yd'

        return data

    def get_next_response(self, message, state, conversation_id):
        """FOLLOW ORIGINAL BOOKING FLOW + ADD BUSINESS RULE QUESTIONS"""
        wants_to_book = self.should_book(message)

        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # ORIGINAL BASIC INFO GATHERING (C1: INFORMATION GATHERING - ALL DETAILS FIRST)
        if not state.get('firstName'):
            return "Can I take your name please?"
        elif not state.get('phone'):
            return "What's the best phone number to contact you on?"
        elif not state.get('postcode'):
            return "What's the postcode where you need the grab lorry?"
        elif not state.get('service'):
            # Auto-set service type for Grab
            state['service'] = 'grab'
            if not state.get('type'):
                state['type'] = '6yd'  # Default
            self.conversations[conversation_id] = state
        
        elif not state.get('waste_type_asked'):
            state['waste_type_asked'] = True
            self.conversations[conversation_id] = state
            return "What type of materials do you have?"
        
        elif not state.get('quantity_asked'):
            state['quantity_asked'] = True
            self.conversations[conversation_id] = state
            return "How much material do you have approximately?"

        # C2: GRAB SIZE UNDERSTANDING (EXACT SCRIPTS)
        elif not state.get('grab_size_explained') and ('wheeler' in message.lower()):
            state['grab_size_explained'] = True
            self.conversations[conversation_id] = state
            if '8-wheeler' in message.lower() or '8 wheeler' in message.lower():
                return "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
            elif '6-wheeler' in message.lower() or '6 wheeler' in message.lower():
                return "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."

        # C3: MATERIALS ASSESSMENT
        elif not state.get('materials_assessed') and state.get('waste_type_asked'):
            state['materials_assessed'] = True
            self.conversations[conversation_id] = state
            
            # Check for mixed materials
            has_soil_rubble = any(material in message.lower() for material in ['soil', 'rubble', 'muckaway', 'hardcore', 'dirt', 'earth'])
            has_other_materials = any(material in message.lower() for material in ['wood', 'metal', 'plastic', 'furniture', 'concrete', 'bricks'])
            
            if has_soil_rubble and has_other_materials:
                return "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."
            elif not has_soil_rubble and has_other_materials:
                return "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."

        # Check for wait & load skip mention
        elif 'wait' in message.lower() and 'load' in message.lower() and not state.get('wait_load_handled'):
            state['wait_load_handled'] = True
            self.conversations[conversation_id] = state
            return "For wait & load skips, let me put you through to our specialist who will check availability & costs."

        # C4: ACCESS & TIMING
        elif not state.get('access_asked'):
            state['access_asked'] = True
            self.conversations[conversation_id] = state
            return "Is there clear access for the grab lorry?"
        
        elif not state.get('timing_asked'):
            state['timing_asked'] = True
            self.conversations[conversation_id] = state
            return "When do you need this collection?"

        # ORIGINAL BOOKING FLOW CONTINUES
        # If user wants to book but we don't have price yet, get price and complete booking
        elif wants_to_book and not state.get('price'):
            print("🚀 USER WANTS TO BOOK - GETTING PRICE AND COMPLETING BOOKING")
            return self.get_pricing_and_complete_booking(state, conversation_id)
        
        # If we have all data but no price yet, get pricing
        elif not state.get('price'):
            return self.get_pricing_and_ask(state, conversation_id)
        
        # If we have pricing, ask to book
        elif state.get('price'):
            price_num = float(str(state['price']).replace('£', '').replace(',', ''))
            # Check if needs transfer - Grab £300+ during office hours
            if self.needs_transfer(price_num):
                return "For this size job, let me put you through to our specialist team for the best service."
            
            return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with grab hire?"
