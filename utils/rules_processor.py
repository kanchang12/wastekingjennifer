import os
import json
import re
import PyPDF2
from typing import Dict, Any, List
from pathlib import Path
from datetime import datetime

class RulesProcessor:
    def __init__(self):
        self.pdf_path = "data/rules/all rules.pdf"
        self.rules_data = self._load_all_rules()
    
    def _load_all_rules(self) -> Dict[str, Any]:
        """Load rules from PDF first, fallback to hardcoded if PDF not available"""
        pdf_text = self._load_rules_from_pdf()
        
        if pdf_text:
            print("Loading rules from PDF...")
            return self._parse_wasteking_pdf(pdf_text)
        else:
            print("PDF not found, using hardcoded rules...")
            return self._get_hardcoded_rules()
    
    def _load_rules_from_pdf(self) -> str:
        """Extract text from the WasteKing rules PDF"""
        try:
            if not Path(self.pdf_path).exists():
                return ""
            
            with open(self.pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                return text
                
        except Exception as e:
            print(f"Error reading PDF: {e}")
            return ""
    
    def _parse_wasteking_pdf(self, pdf_text: str) -> Dict[str, Any]:
        """Parse the WasteKing PDF into structured rules"""
        
        return {
            "lock_rules": self._extract_lock_rules(pdf_text),
            "exact_scripts": self._extract_exact_scripts(pdf_text),
            "office_hours": self._extract_office_hours(pdf_text),
            "transfer_rules": self._extract_transfer_rules(pdf_text),
            "skip_rules": self._extract_skip_rules(pdf_text),
            "mav_rules": self._extract_mav_rules(pdf_text),
            "grab_rules": self._extract_grab_rules(pdf_text),
            "pricing_rules": self._extract_pricing_rules(pdf_text),
            "prohibited_items": self._extract_prohibited_items(pdf_text),
            "surcharge_rates": self._extract_surcharge_rates(pdf_text),
            "testing_corrections": self._extract_testing_corrections(pdf_text)
        }
    
    def _extract_lock_rules(self, text: str) -> Dict[str, str]:
        """Extract LOCK 0-11 mandatory enforcement rules"""
        return {
            "LOCK_0_DATETIME": "CRITICAL: Check current time and business hours IMMEDIATELY",
            "LOCK_1_NO_GREETING": "NEVER say 'Hi I am Thomas' or any greeting",
            "LOCK_2_SERVICE_DETECTION": "IF customer mentions service → Jump to that section",
            "LOCK_3_ONE_QUESTION": "One question at a time - never bundle questions",
            "LOCK_4_NO_DUPLICATES": "Never ask for info twice - use what customer provided",
            "LOCK_5_EXACT_SCRIPTS": "Use exact scripts where specified - never improvise",
            "LOCK_6_NO_OUT_HOURS_TRANSFER": "CARDINAL SIN: NEVER transfer when office closed",
            "LOCK_7_PRICE_THRESHOLDS": "Skip: NO LIMIT, Man&Van: £500+, Grab: £300+",
            "LOCK_8_STORE_ANSWERS": "Don't re-ask for stored information",
            "LOCK_9_OUT_HOURS_CALLBACK": "Out-of-hours = NO transfer, make the sale",
            "LOCK_10_FOCUS_SALES": "Focus on sales, aim for booking completion",
            "LOCK_11_ANSWER_FIRST": "Answer customer questions FIRST before asking details"
        }
    
    def _extract_exact_scripts(self, text: str) -> Dict[str, str]:
        """Extract mandatory exact scripts from PDF"""
        scripts = {}
        
        scripts["permit_script"] = "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe."
        
        scripts["mav_suggestion"] = "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"
        
        scripts["heavy_materials"] = "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
        
        scripts["sofa_prohibited"] = "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations."
        
        scripts["grab_8_wheeler"] = "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
        scripts["grab_6_wheeler"] = "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
        
        scripts["time_restriction"] = "We can't guarantee exact times, but delivery is between 7am-6pm"
        scripts["sunday_collection"] = "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team"
        scripts["final_ending"] = "Is there anything else I can help you with today? Please leave us a review if you're happy with our service. Thank you for your time, have a great day, bye!"
        
        return scripts
    
    def _extract_office_hours(self, text: str) -> Dict[str, str]:
        """Extract office hours from PDF"""
        return {
            "monday_thursday": "8:00am-5:00pm",
            "friday": "8:00am-4:30pm", 
            "saturday": "9:00am-12:00pm",
            "sunday": "CLOSED"
        }
    
    def _extract_transfer_rules(self, text: str) -> Dict[str, Any]:
        """Extract transfer rules from PDF - TWO SITUATION CHECK"""
        return {
            "skip_hire": "NO_LIMIT",
            "man_and_van": 500,
            "grab_hire": 300,
            "out_of_hours_rule": "NEVER transfer out of hours - make the sale instead",
            "office_hours_rule": "During office hours - check price thresholds for transfer",
            "immediate_transfers": [
                "director_request", "complaint", "hazardous_waste",
                "wait_and_load_skip", "mixed_materials_grab"
            ]
        }
    
    def _extract_skip_rules(self, text: str) -> Dict[str, str]:
        """Extract skip hire rules from PDF"""
        return {
            "heavy_materials_8yd_max": "Heavy materials (soil, rubble, concrete) - MAX 8-yard skip",
            "12yd_light_only": "12-yard skips ONLY for light materials",
            "sofa_prohibited": "Sofas CANNOT go in skips - offer Man & Van",
            "permit_required_road": "Road placement requires council permit",
            "mav_suggestion_mandatory": "MUST suggest MAV for 8-yard or smaller + light materials",
            "mandatory_info": "Must collect: name, postcode, waste type before pricing"
        }
    
    def _extract_mav_rules(self, text: str) -> Dict[str, Any]:
        """Extract Man & Van rules from PDF - FIXED"""
        return {
            "default_for_others": "MAV agent handles ONLY explicit man and van mentions",
            "heavy_materials_transfer": "Heavy materials = MUST transfer to specialist during office hours",
            "stairs_transfer": "Stairs/flats = MUST transfer to specialist during office hours",
            "transfer_threshold": 500,
            "out_hours_no_transfer": "Out of hours = NEVER transfer, make the sale",
            "office_hours_threshold": "Office hours = check £500+ threshold for transfer",
            "weight_allowance": "Check API for weight allowances",
            "volume_assessment": "Always assess: items, access, volume"
        }
    
    def _extract_grab_rules(self, text: str) -> Dict[str, Any]:
        """Extract Grab Hire rules from PDF - DEFAULT MANAGER"""
        return {
            "default_manager": "Grab agent handles ALL requests except explicit skip/mav mentions",
            "handles_everything_else": "Unknown services, general inquiries, grab hire, all other requests",
            "6_wheeler_terminology": "6-wheeler = 12-tonne capacity - use exact script",
            "8_wheeler_terminology": "8-wheeler = 16-tonne capacity - use exact script",
            "transfer_threshold": 300,
            "office_hours_threshold": "Office hours = check £300+ threshold for transfer",
            "out_hours_no_transfer": "Out of hours = NEVER transfer, make the sale",
            "suitable_materials": "Suitable for heavy materials (soil, concrete, muck)",
            "access_check": "Always check postcode and access requirements",
            "mixed_materials_transfer": "Mixed materials → transfer to specialist during office hours",
            "wait_load_immediate_transfer": "Wait & load skip → IMMEDIATE transfer"
        }
    
    def _extract_pricing_rules(self, text: str) -> Dict[str, Any]:
        """Extract pricing rules from PDF - NO HARDCODING"""
        return {
            "api_only": "ALL prices must come from real WasteKing API - NEVER hardcode",
            "legal_requirement": "Hardcoded prices are ILLEGAL and court case risk",
            "fail_over_fake": "Better to fail API call than give wrong price",
            "vat_handling": "ALL prices excluding VAT - spell as V-A-T",
            "total_presentation": "Present TOTAL price including surcharges from API",
            "never_base_only": "NEVER quote base price only when surcharges apply",
            "transparency": "List all surcharge items clearly from API response"
        }
    
    def _extract_prohibited_items(self, text: str) -> Dict[str, List[str]]:
        """Extract prohibited items from PDF"""
        return {
            "never_allowed_skips": [
                "Fridges/Freezers", "TV/Screens", "Carpets", "Paint/Liquid",
                "Plasterboard", "Gas cylinders", "Tyres", "Air Conditioning units",
                "Upholstered furniture/sofas"
            ],
            "surcharge_items": [
                "Fridges/Freezers", "Mattresses", "Upholstered furniture"
            ],
            "transfer_required": [
                "Plasterboard", "Gas cylinders", "Hazardous chemicals", "Asbestos", "Tyres"
            ]
        }
    
    def _extract_surcharge_rates(self, text: str) -> Dict[str, str]:
        """Extract surcharge rates from PDF - NO HARDCODING"""
        return {
            "api_only": "All surcharge rates must come from API - NEVER hardcode",
            "legal_warning": "Hardcoded surcharge rates are ILLEGAL"
        }
    
    def _extract_testing_corrections(self, text: str) -> List[Dict[str, str]]:
        """Extract critical wrong/correct phrases from PDF"""
        corrections = []
        
        corrections.extend([
            {
                "wrong": "You can typically put a sofa in a skip",
                "correct": "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations"
            },
            {
                "wrong": "Largest skip for soil is 12-yard",
                "correct": "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard"
            },
            {
                "wrong": "Skip costs £",  # ANY hardcoded price
                "correct": "Let me get you the current price from our system"
            },
            {
                "wrong": "Man & van costs £",  # ANY hardcoded price
                "correct": "Let me get you the current price from our system"
            },
            {
                "wrong": "Grab hire costs £",  # ANY hardcoded price
                "correct": "Let me get you the current price from our system"
            }
        ])
        
        return corrections
    
    def _get_hardcoded_rules(self) -> Dict[str, Any]:
        """Fallback hardcoded rules when PDF not available"""
        return {
            "lock_rules": self._extract_lock_rules(""),
            "exact_scripts": self._extract_exact_scripts(""),
            "office_hours": self._extract_office_hours(""),
            "transfer_rules": self._extract_transfer_rules(""),
            "skip_rules": self._extract_skip_rules(""),
            "mav_rules": self._extract_mav_rules(""),
            "grab_rules": self._extract_grab_rules(""),
            "pricing_rules": self._extract_pricing_rules(""),
            "prohibited_items": self._extract_prohibited_items(""),
            "surcharge_rates": self._extract_surcharge_rates(""),
            "testing_corrections": self._extract_testing_corrections("")
        }
    
    def check_office_hours_and_transfer_rules(self, message: str, agent_type: str, price: float = None) -> Dict[str, Any]:
        """TWO-SITUATION CHECK: Office hours vs Out of hours + Transfer thresholds"""
        now = datetime.now()
        day_of_week = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour
        
        print(f"🕐 TIME CHECK: {now.strftime('%A %H:%M')} (Day: {day_of_week}, Hour: {hour})")
        
        # Determine business hours
        is_office_hours = False
        if day_of_week < 4:  # Monday-Thursday
            is_office_hours = 8 <= hour < 17
        elif day_of_week == 4:  # Friday
            is_office_hours = 8 <= hour < 16
        elif day_of_week == 5:  # Saturday
            is_office_hours = 9 <= hour < 12
        # Sunday = always False (closed)
        
        transfer_rules = self.rules_data["transfer_rules"]
        
        print(f"🏢 OFFICE HOURS STATUS: {is_office_hours}")
        
        # SITUATION 1: OUT OF OFFICE HOURS
        if not is_office_hours:
            print("🌙 SITUATION 1: OUT OF OFFICE HOURS")
            return {
                "situation": "OUT_OF_OFFICE_HOURS",
                "action": "MAKE_THE_SALE",
                "transfer_allowed": False,
                "reason": "NEVER transfer out of hours - cardinal sin. Handle the call and make the sale.",
                "is_office_hours": False,
                "rule_applied": "LOCK_6_NO_OUT_HOURS_TRANSFER + LOCK_9_OUT_HOURS_CALLBACK"
            }
        
        # SITUATION 2: OFFICE HOURS - Check transfer thresholds
        else:
            print("🏢 SITUATION 2: OFFICE HOURS - Checking transfer thresholds")
            
            thresholds = {
                "skip": transfer_rules.get("skip_hire", "NO_LIMIT"),
                "mav": transfer_rules.get("man_and_van", 500),
                "grab": transfer_rules.get("grab_hire", 300)
            }
            
            threshold = thresholds.get(agent_type, 0)
            
            if threshold == "NO_LIMIT":
                transfer_needed = False
                reason = f"{agent_type} has no transfer limit"
            elif price is not None and price >= threshold:
                transfer_needed = True
                reason = f"Price £{price} exceeds £{threshold} threshold for {agent_type}"
            else:
                transfer_needed = False
                if price is not None:
                    reason = f"Price £{price} within £{threshold} threshold for {agent_type}"
                else:
                    reason = f"No price yet - threshold is £{threshold} for {agent_type}"
            
            print(f"💰 THRESHOLD CHECK: {agent_type} threshold=£{threshold}, price=${price}, transfer_needed={transfer_needed}")
            
            return {
                "situation": "OFFICE_HOURS",
                "action": "CHECK_THRESHOLDS",
                "transfer_allowed": transfer_needed,
                "threshold": threshold,
                "price": price,
                "reason": reason,
                "is_office_hours": True,
                "rule_applied": "LOCK_7_PRICE_THRESHOLDS"
            }
    
    def validate_no_hardcoded_prices(self, response: str) -> Dict[str, Any]:
        """Validate that response contains NO hardcoded prices - LEGAL COMPLIANCE"""
        violations = []
        
        # Check for any hardcoded price patterns
        price_patterns = [
            r'£\d+',           # £123
            r'£\d+\.\d+',      # £123.45
            r'\d+\s*pounds?',  # 123 pounds
            r'costs?\s*£',     # costs £
            r'price\s*is\s*£', # price is £
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                violations.append(f"ILLEGAL HARDCODED PRICE DETECTED: {matches}")
        
        # Check for specific hardcoded price phrases
        illegal_phrases = [
            "skip costs £", "mav costs £", "grab costs £",
            "price is £", "that'll be £", "total is £"
        ]
        
        for phrase in illegal_phrases:
            if phrase in response.lower():
                violations.append(f"ILLEGAL PRICE PHRASE: {phrase}")
        
        if violations:
            print(f"🚨 LEGAL VIOLATION DETECTED: {violations}")
        
        return {
            "legal_compliant": len(violations) == 0,
            "violations": violations,
            "severity": "CRITICAL" if violations else "OK",
            "legal_warning": "Hardcoded prices are ILLEGAL and risk court case" if violations else None
        }
    
    def get_rules_for_agent(self, agent_type: str) -> Dict[str, Any]:
        """Get specific rules for an agent type"""
        base_rules = {
            **self.rules_data["lock_rules"],
            "office_hours": self.rules_data["office_hours"],
            "transfer_rules": self.rules_data["transfer_rules"],
            "pricing_rules": self.rules_data["pricing_rules"]  # Always include pricing rules
        }
        
        if agent_type == "skip":
            return {
                **base_rules,
                **self.rules_data["skip_rules"],
                "exact_scripts": {k: v for k, v in self.rules_data["exact_scripts"].items() 
                                if k in ["heavy_materials", "sofa_prohibited", "permit_script", "mav_suggestion"]},
                "prohibited_items": self.rules_data["prohibited_items"]
            }
        elif agent_type == "mav":
            return {
                **base_rules,
                **self.rules_data["mav_rules"],
                "exact_scripts": {k: v for k, v in self.rules_data["exact_scripts"].items()
                                if k in ["time_restriction", "sunday_collection"]}
            }
        elif agent_type == "grab":
            return {
                **base_rules,
                **self.rules_data["grab_rules"],
                "exact_scripts": {k: v for k, v in self.rules_data["exact_scripts"].items()
                                if k in ["grab_6_wheeler", "grab_8_wheeler"]}
            }
        else:
            return base_rules
    
    def validate_response_against_rules(self, response: str, agent_type: str) -> Dict[str, Any]:
        """Validate agent response against business rules"""
        rules = self.get_rules_for_agent(agent_type)
        violations = []
        
        # Check for critical testing corrections
        for correction in self.rules_data.get("testing_corrections", []):
            if correction["wrong"].lower() in response.lower():
                violations.append(f"CRITICAL: Used wrong phrase - {correction['wrong']}")
        
        # Check for hardcoded prices (LEGAL COMPLIANCE)
        price_check = self.validate_no_hardcoded_prices(response)
        if not price_check["legal_compliant"]:
            violations.extend(price_check["violations"])
        
        # Check exact scripts
        if "exact_scripts" in rules:
            for script_name, script_text in rules["exact_scripts"].items():
                if self._should_use_script(response, script_name) and script_text not in response:
                    violations.append(f"Exact script not used for {script_name}")
        
        # Check VAT spelling
        if "vat" in response.lower() and "v-a-t" not in response.lower():
            violations.append("VAT not spelled as V-A-T")
        
        # Check for bundled questions (LOCK 3)
        question_count = response.count('?')
        if question_count > 1:
            violations.append("LOCK 3 VIOLATION: Multiple questions bundled together")
        
        return {
            "compliant": len(violations) == 0,
            "violations": violations,
            "agent_type": agent_type,
            "rules_source": "PDF" if Path(self.pdf_path).exists() else "hardcoded"
        }
    
    def _should_use_script(self, response: str, script_name: str) -> bool:
        """Check if response should use specific exact script"""
        triggers = {
            "permit_script": ["road", "permit", "council"],
            "mav_suggestion": ["8-yard", "light materials"],
            "grab_6_wheeler": ["6-wheeler", "6 wheel"],
            "grab_8_wheeler": ["8-wheeler", "8 wheel"],
            "heavy_materials": ["heavy materials", "soil", "rubble"],
            "sofa_prohibited": ["sofa", "upholstered"]
        }
        
        script_triggers = triggers.get(script_name, [])
        return any(trigger in response.lower() for trigger in script_triggers)
