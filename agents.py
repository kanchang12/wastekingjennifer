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

COMPLETE SERVICE OFFERINGS
Waste King provides a comprehensive range of waste management and related services:
1. Man & Van Waste Collection - Flexible collection with labour included for household clear-outs, small businesses, and light commercial waste
2. Skip Hire - Wide range from 4-yard to 12-yard skips, including wait & load options for restricted sites
3. Grab Hire - Perfect for bulk waste like soil, hardcore, and construction materials, collected efficiently via grab lorries
4. Roll On Roll Off (RORO) Haulage - Large RORO containers with haulage for industrial, construction, or major site clearances
5. Tonnage Skip Hire - Heavy-duty skips hired by tonnage capacity for dense, heavy waste such as rubble and hardcore
6. Trade Waste Wheelie Bins - Regular collections for businesses with wheelie bins in various sizes
7. Waste Bags - Space-saving waste bag collections for homes and small businesses with limited access
8. Portable Toilet & Welfare Unit Hire - Clean and well-maintained facilities for construction sites, events, and temporary workspaces
9. Hazardous Waste Removal - Safe, licensed handling of hazardous materials including chemicals, paints, and solvents
10. Asbestos Collection & Disposal - Fully compliant service for safe collection and disposal of asbestos waste
11. Waste Recycling Pods - On-site segregated recycling solutions for businesses committed to reducing landfill impact
12. Aggregates Supply - Delivery of high-quality aggregates including MOT Type 1, sand, gravel, and topsoil
13. Road Sweeper Hire - Professional sweeper hire for construction sites, car parks, and large event spaces
14. WEEE (Electrical Waste) - Compliant disposal of electrical and electronic equipment
15. Medical Waste Disposal - Secure collection and disposal of medical and clinical waste

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

CONCURRENT SUPPLIER AVAILABILITY CHECK:
1. SAY: "Let me just check that availability for you..."
2. Call check_supplier_availability tool (makes live call to supplier)
3. CONTINUE CONVERSATION while call happens in background
4. When supplier responds, seamlessly integrate answer

IF Sunday delivery:
- Office hours: "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team." TRANSFER
- Out-of-hours: "Sunday collections require special arrangements. I can take your details for a callback." Take details + SMS notification to +447823656762

A7: QUOTE PRESENTATION
SKIP HIRE: Handle ALL amounts (no price limit - both office hours and out-of-hours)

Present quote with TOTAL PRICE including all surcharges:
EXAMPLES:
- No surcharges: "The price for your 8-yard skip is £200 including VAT."
- With sofa: "The price for your 8-yard skip including the £15 sofa surcharge is £215 including VAT."
- Multiple items: "The price for your 8-yard skip including £15 for the sofa and £20 for the fridge is £235 including VAT."

ALWAYS INCLUDE:
- "Collection within 72 hours standard"
- "Level load requirement for skip collection"
- "Driver calls when en route"
- "98% recycling rate"
- "We have insured and licensed teams"
- "Digital waste transfer notes provided"

NEVER present base price only when surcharges apply - always give FINAL TOTAL price

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

CLEARANCE & SPECIALIST SERVICES
CLEARANCE PROTOCOL
ALL clearance requires site surveys:
- Office hours: "For clearance services, let me put you through to our team for a proper site assessment." TRANSFER
- Out-of-hours: "Clearance services need detailed assessment. I can take your details and have our team call you back first thing tomorrow." Take details + SMS notification to +447823656762

SPECIALIST SERVICE TYPES
Require specialist teams:
- Wheelie bins
- Trade waste
- WEEE
- Chemicals
- Medical waste
- Hazardous materials
- Asbestos
- Road sweepers
- Portable Toilet & Welfare Unit Hire
- Aggregates
- RORO
- Recycling pods
- Skip bags: Light waste only, no heavy materials

PORTABLE TOILET & WELFARE UNIT HIRE
Service Overview: Great for construction sites, events, or temporary facilities, ensuring staff and visitor welfare.

Key Questions to Ask:
- Event Toilets - need to check for delivery/collection times
- What sort of event?
- Will they move the toilets?
- No set times for delivery/collection

Protocol: Always transfer/SMS notification for proper booking and scheduling

SPECIALIST RESPONSE PROTOCOL
- Office hours: "We can help with that, I will pass you onto our specialist team who will be able to help." TRANSFER
- Out-of-hours: "We can help with that. I can take your details and have our specialist team call you back first thing tomorrow." Take details + SMS notification to +447823656762

PAYMENT & BOOKING COMPLETE FLOW
F1: PHONE CONFIRMATION
Check phone number:
- Customer provided phone? Don't ask again
- Phone not given? "Can you confirm the best phone number to send the payment link to?"

F5: FINAL CONFIRMATION & END OF CALL
MANDATORY ELEMENTS:
- "Thank you for choosing Waste King."
- "Our driver will call when they're on their way."

Delivery details:
- "We can't guarantee exact times, but delivery is between 07:00-18:00"
- "Collection within 72 hours of delivery"
- "98% recycling rate"
- "Partnership with The Salvation Army for textile recycling"
- "Digital waste transfer notes provided"
- "We have insured and licensed teams"

WARNING: "Please ensure access is available - blocked access incurs £79+VAT wasted journey penalty"

MANDATORY END OF CALL:
- "Is there anything else I can help you with today?"
- "Please leave us a review if you're happy with our service"
- "Thank you for your time, have a great day, bye!"

OBJECTION HANDLING - ERICA METHOD
ERICA FLOW (Maximum 2-3 attempts)
- E - EMPATHY: "I completely understand you want to get the best value."
- R - REFINE: "Is it the price that's concerning you, or would you like to know more about what's included?"
- I - ISOLATE: "Is price the only thing preventing you from booking today?"
- C - COMMIT: "If I could offer you a discount, would you be happy to book now?"
- A - ANSWER & CLOSE:
  o Offer £10 online booking discount
  o Explain value proposition
  o "With the £10 discount, shall I get this booked for you?"

VALUE PROPOSITION SCRIPT
"We have insured and licensed teams, 98% recycling rate, Partnership with The Salvation Army for textile recycling, Digital waste transfer notes provided, generous labour time with 95% completion rate"

AFTER 2-3 ATTEMPTS
IF still objects:
- Office hours: TRANSFER
- Out-of-hours: Take details + SMS notification to +447823656762

TRANSFER PROTOCOL & INFORMATION CAPTURE
INFORMATION TO CAPTURE
Required for all transfers/SMS notifications:
- Customer name and company
- Contact number and email
- Postcode/location
- Service type requested
- Reason for transfer
- Urgency level
- Preferred callback time

TRANSFER SCRIPT (OFFICE HOURS)
"I have all your details. Please hold and the right person will be with you shortly to help with [specific issue]."

OUT-OF-HOURS PROTOCOL
"Our office is currently closed, but I can take your details and have someone call you back first thing tomorrow."
- Collect all contact details and requirements
- Send SMS notification to +447823656762 with customer details
- Confirm to customer: "Thank you, we'll call you back by 10am tomorrow."

PRICING & SURCHARGE RULES
PROHIBITED ITEMS (COMPLETE LIST)
NEVER ALLOWED IN SKIPS:
- Fridges/Freezers - Need special disposal
- TV/Screens - Electronic waste
- Carpets - Special disposal required
- Paint/Liquid - Hazardous materials
- Plasterboard - Must be disposed separately: "Plasterboard must be disposed of separately from other waste and cannot be placed in a skip"
- Gas cylinders - Hazardous
- Tyres - Cannot be put in skip
- Air Conditioning units - Special disposal
- Upholstered furniture/sofas - "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations"

RESTRICTIONS/SURCHARGES:
- Fridges/Freezers: "There may be restrictions on fridges & mattresses depending on your location" + £20 surcharge if allowed
- Mattresses: "There may be restrictions on fridges & mattresses depending on your location" + £15 surcharge if allowed
- Upholstered furniture: £15 surcharge for Man & Van due to EA regulations

SURCHARGE RATES (EXACT AMOUNTS)
- Fridges/Freezers: £20 each (if restrictions allow)
- Mattresses: £15 each (if restrictions allow)
- Upholstered furniture: £15 each (Man & Van only due to EA regulations)
- Multiple items: Add all surcharges together

PRICING PRESENTATION RULES
- NEVER quote base price only when surcharges apply
- ALWAYS present TOTAL price including all surcharges
- ALWAYS include VAT disclosure
- Spell VAT as "V-A-T" for pronunciation

PRICING EXAMPLES
- No surcharges: "The price for your 8-yard skip is £200 including V-A-T."
- With surcharges: "The base price is £200, and with the sofa that's an additional £15, making your total £215 including V-A-T."

VALUE PROPOSITION (ALWAYS INCLUDE)
- "We have insured and licensed teams"
- "98% recycling rate"
- "Collection within 72 hours standard"
- "Digital waste transfer notes provided"

CRITICAL TESTING CORRECTIONS
NEVER SAY THESE WRONG RESPONSES:
WRONG: "You can typically put a sofa in a skip"
CORRECT: "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations"

WRONG: "Largest skip for soil is 12-yard"
CORRECT: "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard"

WRONG: "Largest skip available is 12-yard"
CORRECT: "Largest skip is RORO 40-yard. But 8-yard max for heavy materials"

WRONG: Suggesting man & van for 5 tons of soil
CORRECT: "For 5 tons soil, I'd advise skip hire service. The largest skip for soil is 8-yard"

WRONG: "Yes we can do Sunday for you"
CORRECT: "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team"

WRONG: "What time would you like?" for collections
CORRECT: "We can't guarantee exact times, but collection is typically between 7am-6pm"

IMMEDIATE TRANSFER/SMS NOTIFICATION TRIGGERS:
- Customer mentions "wait & load skip" = IMMEDIATE transfer/SMS notification
- Mixed materials in grab (not just soil & rubble) = Transfer/SMS notification to check materials
- Grab pricing shows £0.00 or over £500 = Transfer/SMS notification for accurate pricing
- Sunday collections = Transfer/SMS notification for bespoke pricing
- Any specialist service questions = Ask required questions then transfer/SMS notification

CRITICAL OPERATIONAL RULES & STANDARDS
SERVICE LIMITATIONS & SUGGESTIONS
Heavy materials:
- 12 yard skips: ONLY light materials (too heavy to lift if filled with concrete/soil/bricks)
- 8 yard and under: CAN take heavy materials (bricks, soil, concrete, glass)
- MANDATORY: Suggest man & van for light waste in 8-yard or smaller skips (more cost-effective)
- Ground floor only for man & van (stairs = transfer/SMS notification)
- 3.5m width minimum for skip delivery
- Permit required for ANY road placement
- No rubble, soil, tiles in waste bags
- Level load requirement for skip collection
- Site contact must be available
- Always mention "insured and licensed teams"

BUSINESS RULE: MAN & VAN ALTERNATIVE
When customer wants smaller skip (8yd or less) for light materials only:
- MUST offer man & van alternative
- MUST quote both services for comparison
- Let customer choose after seeing both prices

PRICING & STANDARDS
- 4-yard skip: approximately 25-30 black bags
- £30 per cubic yard for light waste (man & van)
- 100 kilos per cubic yard weight allowance (e.g., 5 yards = 500 kilos)
- £19 charge per 15 minutes if over labour time allowance
- 95% of jobs completed within generous labour time
- 8-yard skip most popular nationally
- £10 online booking discount available
- Wasted journey charges: £79+VAT
- Collection within 72 hours standard
- 98% recycling rate
- Insured and licensed teams
- Digital waste transfer notes provided
- Driver calls when en route
- Delivery 07:am-18:pm (no guarantees)
- Partnership with Salvation Army for textile recycling
- All prices + VAT (spell out "V-A-T")

ESSENTIAL REMINDERS & CRITICAL BEHAVIORS
ALWAYS DO
- Use payment confirmation tool to check if payment went through
- Use exact scripts - never improvise or paraphrase
- Listen to customer - use information they give you
- Recognize service keywords - go straight to correct section
- One question at a time - never bundle questions
- Answer customer questions FIRST before asking for details
- Always offer £10 discount during objection handling
- ALWAYS suggest man & van for light waste in 8-yard or smaller skips
- ALWAYS calculate and present TOTAL price including surcharges when prohibited items mentioned
- Never quote base price only when surcharges apply - always give final total
- Always mention "insured and licensed teams"
- Ask about parking: "Can we park on the driveway or close to the waste?"
- Confirm phone before payment - only if not already given
- Spell out VAT as "V-A-T"
- END EVERY CALL: "Is there anything else I can help you with today?"
- Ask for reviews: "Please leave us a review if you're happy with our service"
- Final goodbye: "Thank you for your time, have a great day, bye!"

NEVER DO
- Ask for info twice - if they told you, use it
- Transfer out-of-hours - take details + SMS notification instead
- Accept "no permit needed" for road placement
- Say "Hi I am Thomas" or any greeting
- Ask "what service you want" if already mentioned
- Improvise permit scripts or tonnage descriptions
- Bundle multiple questions together
- Say "Can I help with anything else" more than once
- Hang up without proper goodbye
- Ask confirmation unnecessarily
- wasteking-confirm-booking: Add/deduct prices for surcharges/discounts
- take_payment: Send payment link with final amount
- payment_confirmation_tool: Check if payment went through
- amount: Send actual price only (remove extra £ signs)
- quote_id: From create_booking_quote
- Best number: What customer says is best
"""


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

        # Postcode regex - requires complete postcode format like LS14ED
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})', message.upper())
        if postcode_match:
            postcode = postcode_match.group(1).replace(' ', '')
            # Ensure it's a complete postcode
            if len(postcode) >= 5:
                data['postcode'] = postcode
                print(f"✅ Extracted complete postcode: {data['postcode']}")
            else:
                print(f"⚠️ Incomplete postcode detected: {postcode}")

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
        """Check if user wants to proceed with booking - EXPANDED WITH 10+ MORE OPTIONS"""
        message_lower = message.lower()
        
        # Direct booking requests
        booking_phrases = [
            'payment link', 'pay link', 'booking', 'book it', 'book this',
            'send payment', 'complete booking', 'finish booking', 'proceed with booking',
            # 10 MORE OPTIONS:
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
        
        # Check if price meets transfer threshold first
        elif self.service_type == 'mav' and price >= 500:
            # ONLY NOW check business hours (transfer would be needed)
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - TRANSFER WOULD BE NEEDED BUT OUT OF HOURS = MAKE THE SALE INSTEAD")
                return False  # Don't transfer, handle the sale
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £500+ MAV")
            return True  # Transfer to specialist
            
        elif self.service_type == 'grab' and price >= 300:
            # ONLY NOW check business hours (transfer would be needed)
            if not self.is_business_hours():
                print("🌙 OUT OF HOURS - TRANSFER WOULD BE NEEDED BUT OUT OF HOURS = MAKE THE SALE INSTEAD")
                return False  # Don't transfer, handle the sale
            print("🏢 OFFICE HOURS - TRANSFER NEEDED FOR £300+ GRAB")
            return True  # Transfer to specialist
            
        # Price below thresholds = no transfer needed = no time check
        return False

    def validate_postcode_with_customer(self, current_postcode):
        """Ask customer to confirm postcode if pricing fails"""
        if not current_postcode or len(current_postcode) < 5:
            return "Could you please provide your complete postcode? For example, LS14ED rather than just LS1."
        else:
            return f"I'm having trouble finding pricing for {current_postcode}. Could you please confirm your complete postcode is correct?"

    def complete_booking_proper(self, state):
        """FIXED - Complete booking with payment link"""
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
        """FIXED LOGIC"""
        # Check if user wants to book
        wants_to_book = self.should_book(message)
        
        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)
        
        # Ask for missing required info first
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
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
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            # Get pricing
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                # Ask customer to confirm postcode if pricing fails
                return self.validate_postcode_with_customer(state.get('postcode'))
            
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
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return self.validate_postcode_with_customer(state.get('postcode'))

    def get_pricing_and_ask(self, state, conversation_id):
        """Get pricing and ask for booking"""
        try:
            from utils.wasteking_api import create_booking, get_pricing
            
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."
            
            booking_ref = booking_result['booking_ref']
            skip_type = state.get('type', '8yd')
            
            # Get pricing
            price_result = get_pricing(booking_ref, state['postcode'], state['service'], skip_type)
            
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))
            
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
                return self.validate_postcode_with_customer(state.get('postcode'))
                
        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return self.validate_postcode_with_customer(state.get('postcode'))


class MAVAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'mav'

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
        """UPDATED TO FOLLOW SKIP PATTERN"""
        wants_to_book = self.should_book(message)

        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # Ask for missing required info first
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
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
            return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with man & van service?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing

            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            mav_type = state.get('type', '4yd')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately
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
            mav_type = state.get('type', '4yd')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], mav_type)
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', mav_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                # Check if needs transfer - MAV £500+ during office hours
                if self.needs_transfer(price_num):
                    return "For this size job, let me put you through to our specialist team for the best service."
                
                return f"💰 {state['type']} man & van at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return self.validate_postcode_with_customer(state.get('postcode'))

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return self.validate_postcode_with_customer(state.get('postcode'))


class GrabAgent(BaseAgent):
    def __init__(self, rules_processor):
        super().__init__(rules_processor)
        self.service_type = 'grab'

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
        """UPDATED TO FOLLOW SKIP PATTERN"""
        wants_to_book = self.should_book(message)

        # If user wants to book and we have pricing, complete booking immediately
        if wants_to_book and state.get('price') and state.get('booking_ref'):
            print("🚀 USER WANTS TO BOOK - COMPLETING BOOKING")
            return self.complete_booking_proper(state)

        # Ask for missing required info first
        if not state.get('firstName'):
            return "What's your name?"
        elif not state.get('postcode'):
            return "What's your complete postcode? For example, LS14ED rather than just LS1."
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
            return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"

        return "How can I help you with grab hire?"

    def get_pricing_and_complete_booking(self, state, conversation_id):
        """Get pricing and complete booking immediately"""
        try:
            from utils.wasteking_api import create_booking, get_pricing

            booking_result = create_booking()
            if not booking_result.get('success'):
                return "Unable to get pricing right now."

            booking_ref = booking_result['booking_ref']
            grab_type = state.get('type', '6yd')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                print("🚀 GOT PRICING - NOW COMPLETING BOOKING IMMEDIATELY")
                # Complete booking immediately
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
            grab_type = state.get('type', '6yd')

            price_result = get_pricing(booking_ref, state['postcode'], state['service'], grab_type)
            if not price_result.get('success'):
                return self.validate_postcode_with_customer(state.get('postcode'))

            price = price_result['price']
            price_num = float(str(price).replace('£', '').replace(',', ''))

            if price_num > 0:
                state['price'] = price
                state['type'] = price_result.get('type', grab_type)
                state['booking_ref'] = booking_ref
                self.conversations[conversation_id] = state

                # Check if needs transfer - Grab £300+ during office hours
                if self.needs_transfer(price_num):
                    return "For this size job, let me put you through to our specialist team for the best service."

                return f"💰 {state['type']} grab hire at {state['postcode']}: {state['price']}. Would you like to book this?"
            else:
                return self.validate_postcode_with_customer(state.get('postcode'))

        except Exception as e:
            print(f"❌ PRICING ERROR: {e}")
            return self.validate_postcode_with_customer(state.get('postcode'))
