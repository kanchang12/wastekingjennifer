import re
import json
import os
import requests
from datetime import datetime
from utils.wasteking_api import complete_booking

# Define business rules from PDF - COMPLETE RULES
rules_text = """
WASTE KING AI VOICE AGENT COMPLETE BUSINESS RULES MANUAL

OFFICE HOURS & TRANSFER RULES
OPERATING HOURS:
- Monday-Thursday: 8:00am-5:00pm
- Friday: 8:00am-4:30pm
- Saturday: 9:00am-12:00pm
- All other times: OUT OF HOURS

TRANSFER THRESHOLDS
IMMEDIATE TRANSFER/NOTIFICATION CONDITIONS
Management/Director Requests
"Can I speak to Glenn Currie/director?"
- Take name and reason for calling
- Office hours: I am sorry, Glenn is not available, may I take your details and Glenn will call you back?
- Out-of-hours: Take full details + SMS notification to +447823656762 + tell customer "I can take your details and have our director call you back first thing tomorrow"

Complaints
- Office hours: "I understand your frustration, please bear with me while I transfer you to the appropriate person." TRANSFER
- Out-of-hours: "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow." Take details + SMS notification to +447823656762

Specialist Services (Always Transfer/Callback)
- Hazardous waste disposal
- Asbestos removal/collection
- WEEE electrical waste
- Chemical disposal
- Medical waste
- Trade waste
- Wheelie bins
Office hours: Transfer immediately Out-of-hours: Take details + SMS notification to +447823656762

SKIP HIRE COMPLETE FLOW
A1: INFORMATION GATHERING SEQUENCE
Check what customer already provided:
- Name given? Skip to next
- Postcode given? Confirm: "Can you confirm [postcode] is correct?"
- Waste type given? Skip to next
- Missing info? Ask ONLY what's missing

IF postcode not in marketplace tool:
- Confirm postcode (may have heard wrong)
- Office hours: Transfer
- Out-of-hours: Take details + SMS notification to +447823656762

A2: HEAVY MATERIALS CHECK & MAN & VAN SUGGESTION
Ask: "What are you going to keep in the skip?"
HEAVY MATERIALS RULES:
- 12 yard skips: ONLY light materials (no concrete, soil, bricks - too heavy to lift)
- 8 yard and under: CAN take heavy materials (bricks, soil, concrete, glass)

IF 12 yard skip + heavy materials mentioned: "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."

CRITICAL BUSINESS RULE - MAN & VAN SUGGESTION: IF 8 yard or smaller skip + LIGHT MATERIALS ONLY (no heavy items mentioned):
SAY EXACTLY: "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"
- If customer says YES: Use marketplace tool for BOTH skip AND man & van quotes, present both prices
- If customer says NO or prefers skip: Continue with skip process

A3: SKIP SIZE & LOCATION
Check what customer said:
- Size mentioned? Use it, don't ask again
- Size not mentioned? "What size skip are you thinking of?"
- If unsure: "We have 4, 6, 8, and 12-yard skips. Our 8-yard is most popular nationally."

Check location:
- Location mentioned? Use it, don't ask again
- Location not mentioned? "Will the skip go on your driveway or on the road?"

IF road/street/outside/in front/pavement: MANDATORY PERMIT SCRIPT
IF driveway/private land: No permit needed, continue

PERMIT SCRIPT (EXACT WORDS)
SAY EXACTLY: "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe."

Ask EXACTLY:
1. "Are there any parking bays where the skip will go?"
2. "Are there yellow lines in that area?"
3. "Are there any parking restrictions on that road?"

NEVER accept customer saying "no permit needed"

A4: ACCESS ASSESSMENT
Ask: "Is there easy access for our lorry to deliver the skip?" Ask: "Any low bridges, narrow roads, or parking restrictions?"
CRITICAL: 3.5m width minimum required

IF complex access:
- Office hours: "For complex access situations, let me put you through to our team for a site assessment." TRANSFER
- Out-of-hours: "For complex access situations, I can take your details and have our team call you back first thing tomorrow for a site assessment." Take details + SMS notification to +447823656762

A5: PROHIBITED ITEMS SCREENING for SKIPS
Ask: "Do you have any of these items?"

STANDARD SURCHARGE ITEMS (ADD TO QUOTE IMMEDIATELY):
- Fridges/Freezers (£20+ extra) - Need degassing
- Mattresses (£15+ extra)
- Upholstered furniture/sofas (£15+ extra)

WHEN CUSTOMER MENTIONS SURCHARGE ITEMS:
1. Get base price from marketplace tool
2. IMMEDIATELY calculate total with surcharges
3. Present FINAL price including surcharges

EXAMPLE: "The base price is £200, and with the sofa that's an additional £15, making your total £215 including VAT."

TRANSFER REQUIRED ITEMS:
- Plasterboard: "Plasterboard requires a separate skip."
- Gas cylinders, paints, hazardous chemicals: "We can help with hazardous materials."
- Asbestos: Always transfer/SMS notification
- Tyres: "Tyres can't be put in skip"

A6: TIMING & QUOTE GENERATION
Check timing:
- Customer mentioned timing? Use it, don't ask again
- Timing not given? "When do you need this delivered?"

SAY EXACTLY: "We can't guarantee exact times, but delivery is between SEVEN AM TO SIX PM"

A7: QUOTE PRESENTATION
SKIP HIRE: Handle ALL amounts (no price limit - both office hours and out-of-hours)

Present quote with TOTAL PRICE including all surcharges:
EXAMPLES:
- No surcharges: "The price for your 8-yard skip is £200 including VAT."
- With sofa: "The price for your 8-yard skip including the £15 sofa surcharge is £215 including VAT."

ALWAYS INCLUDE:
- "Collection within 72 hours standard"
- "Level load requirement for skip collection"
- "Driver calls when en route"
- "98% recycling rate"
- "We have insured and licensed teams"
- "Digital waste transfer notes provided"

MAN & VAN COMPLETE FLOW
B1: INFORMATION GATHERING
Check what customer already provided:
- Name given? Skip to next
- Postcode given? Skip to next
- Waste type given? Skip to next
- Missing info? Ask ONLY what's missing

B2: HEAVY MATERIALS CHECK
Ask: "Do you have soil, rubble, bricks, concrete, or tiles?"

IF YES:
- Office hours: "For heavy materials with man & van service, let me put you through to our specialist team for the best solution." TRANSFER
- Out-of-hours: "For heavy materials with man & van, I can take your details for our specialist team to call back." Take details + SMS notification to +447823656762

IF NO: Continue to volume assessment

B3: VOLUME ASSESSMENT & WEIGHT LIMITS
Check amount:
- Customer described amount? Don't ask again
- Amount not clear? "How much waste do you have approximately?"

SAY EXACTLY: "We charge by the cubic yard at £30 per yard for light waste."

WEIGHT ALLOWANCES:
- "We allow 100 kilos per cubic yard - for example, 5 yards would be 500 kilos"
- "The majority of our collections are done under our generous weight allowances"

LABOUR TIME:
- "We allow generous labour time and 95% of all our jobs are done within the time frame"
- "Although if the collection goes over our labour time, there is a £19 charge per 15 minutes"

If unsure: "Think in terms of washing machine loads or black bags." Reference: "National average is 6 yards for man & van service."

B4: ACCESS ASSESSMENT (CRITICAL)
Ask:
- "Where is the waste located and how easy is it to access?"
- "Can we park on the driveway or close to the waste?"
- CRITICAL: "Are there any stairs involved?"
- "How far is our parking from the waste?"

ALWAYS MENTION: "We have insured and licensed teams"

IF stairs/flats/apartments:
- Office hours: "For collections involving stairs, let me put you through to our team for proper assessment." TRANSFER
- Out-of-hours: "Collections involving stairs need special assessment. I can arrange a callback." Take details + SMS notification to +447823656762

B5: ADDITIONAL ITEMS & TIMING
Ask: "Is there anything else you need removing while we're on site?"

Check prohibited items (same surcharge rules as skip hire):
- Fridges/Freezers: +£20 each (if allowed)
- Mattresses: +£15 each (if allowed)
- Upholstered furniture: +£15 each (due to EA regulations)

CRITICAL TIME RESTRICTIONS: NEVER guarantee specific times SAY: "We can't guarantee exact times, but collection is typically between 7am-6pm"

SUNDAY COLLECTIONS: IF customer requests Sunday collection: SAY EXACTLY: "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team and they will be able to help"

B6: QUOTE & PRICING DECISION
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

        # Extract names
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

        # Extract waste type information
        if any(waste in message_lower for waste in ['plastic', 'household', 'furniture', 'clothes', 'books', 'toys', 'cardboard', 'paper']):
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
            
            if waste_types:
                data['waste_type'] = ', '.join(waste_types)
                print(f"✅ Extracted waste type: {data['waste_type']}")

        # Extract location information
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
            
        # Check for positive responses
        return any(word in message_lower for word in positive_words)

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
        """Check if transfer is needed based on price thresholds"""
        if self.service_type == 'skip':
            return False  # Skip has NO_LIMIT - never transfer
        
        elif self.service_type == 'mav' and price >= 500:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - TRANSFER WOULD BE NEEDED BUT OUT OF HOURS = MAKE THE SALE INSTEAD")
                return False
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £500+ MAV")
            return True
            
        elif self.service_type == 'grab' and price >= 300:
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - TRANSFER WOULD BE NEEDED BUT OUT OF HOURS = MAKE THE SALE INSTEAD")
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
        """Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self.default_type)
            
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                return self.complete_booking_proper(state)
            else:
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return self.validate_postcode_with_customer(state.get('postcode'))

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            service_type = state.get('type', self.default_type)
            
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], service_type)
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))
            
            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))
            
            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', service_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state
                
                # Check if needs transfer
                if self.needs_transfer(price_num):
                    return "For this size job, let me put you through to our specialist team for the best service."
                
                return f"💰 {state['type']} {self.service_name} at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return self.validate_postcode_with_customer(state.get('postcode'))


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

    def get_next_response(self, message, state, conversation_id):
        """FOLLOW ORIGINAL BOOKING FLOW + ADD BUSINESS RULE QUESTIONS"""
        wants_to_book = self.should_book(message)
        message_lower = message.lower()
        
        # CAPTURE USER ANSWERS AND STORE IN STATE
        # Capture name if provided in any message
        if not state.get('firstName') and any(word in message for word in ['name is', 'my name', 'i am', 'i\'m']):
            name_match = re.search(r'(?:name is|my name|i am|i\'m)\s+([A-Z][a-z]+)', message, re.IGNORECASE)
            if name_match:
                state['firstName'] = name_match.group(1)
        
        # Capture phone if provided in any message
        if not state.get('phone'):
            phone_match = re.search(r'\b(\d{10,11})\b', message)
            if phone_match:
                state['phone'] = phone_match.group(1)
        
        # Capture postcode if provided in any message
        if not state.get('postcode'):
            postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
            if postcode_match:
                postcode = postcode_match.group(1).replace(' ', '')
                if len(postcode) >= 5:
                    state['postcode'] = postcode
        
        # Capture waste content answer
        if state.get('waste_content_asked') and not state.get('materials_assessed'):
            state['waste_content'] = message
            if any(heavy in message_lower for heavy in ['concrete', 'soil', 'brick', 'rubble', 'hardcore', 'stone', 'tile']):
                state['has_heavy_materials'] = True
            else:
                state['has_heavy_materials'] = False
        
        # Capture location answer
        if state.get('location_asked') and not state.get('permit_handled'):
            state['location_details'] = message
            if any(road in message_lower for road in ['road', 'street', 'outside', 'front', 'pavement', 'highway', 'public']):
                state['needs_permit'] = True
            else:
                state['needs_permit'] = False
        
        # Capture prohibited items answer
        if state.get('prohibited_items_asked'):
            state['prohibited_items'] = message
            if any(item in message_lower for item in ['fridge', 'freezer', 'mattress', 'sofa', 'upholstered', 'couch']):
                state['has_surcharge_items'] = True
            else:
                state['has_surcharge_items'] = False
        
        # Capture timing answer
        if state.get('timing_asked'):
            state['delivery_timing'] = message
        
        # Save the updated state
        self.conversations[conversation_id] = state
        
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
            if state.get('type') == '12yd' and state.get('has_heavy_materials'):
                return "For 12 yard skips, we can only take light materials as heavy materials make the skip too heavy to lift. For heavy materials, I'd recommend an 8 yard skip or smaller."
            # MAN & VAN SUGGESTION for 8yd or smaller with light materials
            elif state.get('type') in ['8yd', '6yd', '4yd'] and not state.get('has_heavy_materials'):
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
        elif not state.get('permit_handled') and state.get('needs_permit'):
            state['permit_handled'] = True
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
    def __init__(self, rules_processor=None):
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
        message_lower = message.lower()
        
        # CAPTURE USER ANSWERS AND STORE IN STATE
        # Capture basic info from any message
        if not state.get('firstName') and any(word in message for word in ['name is', 'my name', 'i am', 'i\'m']):
            name_match = re.search(r'(?:name is|my name|i am|i\'m)\s+([A-Z][a-z]+)', message, re.IGNORECASE)
            if name_match:
                state['firstName'] = name_match.group(1)
        
        if not state.get('phone'):
            phone_match = re.search(r'\b(\d{10,11})\b', message)
            if phone_match:
                state['phone'] = phone_match.group(1)
        
        if not state.get('postcode'):
            postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
            if postcode_match:
                postcode = postcode_match.group(1).replace(' ', '')
                if len(postcode) >= 5:
                    state['postcode'] = postcode
        
        # Capture heavy materials answer
        if state.get('heavy_materials_checked'):
            if any(heavy in message_lower for heavy in ['soil', 'rubble', 'brick', 'concrete', 'tile', 'stone']):
                state['has_heavy_materials'] = True
            else:
                state['has_heavy_materials'] = False
        
        # Capture waste type answer
        if not state.get('waste_type') and state.get('heavy_materials_checked'):
            state['waste_type'] = message
        
        # Capture volume answer
        if state.get('volume_assessed'):
            state['waste_volume'] = message
        
        # Capture location answer
        if not state.get('location') and state.get('volume_assessed'):
            state['location'] = message
        
        # Capture parking answer
        if state.get('parking_checked'):
            state['parking_details'] = message
        
        # Capture stairs answer
        if state.get('stairs_checked'):
            if any(word in message_lower for word in ['stairs', 'staircase', 'upstairs', 'steps', 'flight']):
                state['has_stairs'] = True
            else:
                state['has_stairs'] = False
        
        # Capture distance answer
        if state.get('distance_checked'):
            state['distance_details'] = message
        
        # Capture additional items answer
        if state.get('additional_items_checked'):
            if any(item in message_lower for item in ['fridge', 'freezer', 'mattress', 'sofa', 'upholstered']):
                state['has_additional_items'] = True
            else:
                state['has_additional_items'] = False
        
        # Capture timing answer
        if state.get('timing_checked'):
            state['collection_timing'] = message
        
        # Save the updated state
        self.conversations[conversation_id] = state

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
    def __init__(self, rules_processor=None):
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
        message_lower = message.lower()
        
        # CAPTURE USER ANSWERS AND STORE IN STATE
        # Capture basic info from any message
        if not state.get('firstName') and any(word in message for word in ['name is', 'my name', 'i am', 'i\'m']):
            name_match = re.search(r'(?:name is|my name|i am|i\'m)\s+([A-Z][a-z]+)', message, re.IGNORECASE)
            if name_match:
                state['firstName'] = name_match.group(1)
        
        if not state.get('phone'):
            phone_match = re.search(r'\b(\d{10,11})\b', message)
            if phone_match:
                state['phone'] = phone_match.group(1)
        
        if not state.get('postcode'):
            postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
            if postcode_match:
                postcode = postcode_match.group(1).replace(' ', '')
                if len(postcode) >= 5:
                    state['postcode'] = postcode
        
        # Capture waste type answer
        if state.get('waste_type_asked'):
            state['waste_type'] = message
            if any(material in message_lower for material in ['soil', 'rubble', 'muckaway', 'hardcore']):
                state['has_soil_rubble'] = True
            if any(material in message_lower for material in ['wood', 'metal', 'plastic', 'furniture', 'concrete', 'bricks']):
                state['has_other_materials'] = True
        
        # Capture quantity answer
        if state.get('quantity_asked'):
            state['material_quantity'] = message
        
        # Capture access answer
        if state.get('access_asked'):
            state['access_details'] = message
        
        # Capture timing answer
        if state.get('timing_asked'):
            state['collection_timing'] = message
        
        # Save the updated state
        self.conversations[conversation_id] = state
        
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
        elif not state.get('grab_size_explained') and ('wheeler' in message_lower):
            state['grab_size_explained'] = True
            self.conversations[conversation_id] = state
            if '8-wheeler' in message_lower or '8 wheeler' in message_lower:
                return "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
            elif '6-wheeler' in message_lower or '6 wheeler' in message_lower:
                return "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."

        # C3: MATERIALS ASSESSMENT
        elif not state.get('materials_assessed') and state.get('waste_type_asked'):
            state['materials_assessed'] = True
            self.conversations[conversation_id] = state
            
            # Check for mixed materials using captured state
            if state.get('has_soil_rubble') and state.get('has_other_materials'):
                return "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."
            elif not state.get('has_soil_rubble') and state.get('has_other_materials'):
                return "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you."

        # Check for wait & load skip mention
        elif 'wait' in message_lower and 'load' in message_lower and not state.get('wait_load_handled'):
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
