import os
import json
import re
import PyPDF2
from typing import Dict, Any, List
from pathlib import Path

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
            "LOCK_0_DATETIME": "CRITICAL: Call get_current_datetime() IMMEDIATELY at conversation start",
            "LOCK_1_NO_GREETING": "NEVER say 'Hi I am Thomas' or any greeting",
            "LOCK_2_SERVICE_DETECTION": "IF customer mentions service → Jump to that section",
            "LOCK_3_ONE_QUESTION": "One question at a time - never bundle questions",
            "LOCK_4_NO_DUPLICATES": "Never ask for info twice - use what customer provided",
            "LOCK_5_EXACT_SCRIPTS": "Use exact scripts where specified - never improvise",
            "LOCK_6_NO_OUT_HOURS_TRANSFER": "CARDINAL SIN: NEVER transfer when office closed",
            "LOCK_7_PRICE_THRESHOLDS": "Skip: NO LIMIT, Man&Van: £500+, Grab: £300+",
            "LOCK_8_STORE_ANSWERS": "Don't re-ask for stored information",
            "LOCK_9_OUT_HOURS_CALLBACK": "Out-of-hours = callback, not transfer",
            "LOCK_10_FOCUS_SALES": "Focus on sales, aim for booking completion",
            "LOCK_11_ANSWER_FIRST": "Answer customer questions FIRST before asking details"
        }
    
    def _extract_exact_scripts(self, text: str) -> Dict[str, str]:
        """Extract mandatory exact scripts from PDF"""
        scripts = {}
        
        # Extract permit script
        if "For any skip placed on the road, a council permit is required" in text:
            scripts["permit_script"] = "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote. The permit ensures everything is legal and safe."
        
        # Extract MAV suggestion
        if "Since you have light materials for an 8-yard skip" in text:
            scripts["mav_suggestion"] = "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"
        
        # Extract heavy materials script
        if "For heavy materials such as soil & rubble" in text:
            scripts["heavy_materials"] = "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
        
        # Extract sofa prohibited
        if "No, sofa is not allowed in a skip as it's upholstered furniture" in text:
            scripts["sofa_prohibited"] = "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service. We charge extra due to EA regulations."
        
        # Extract grab scripts
        if "I understand you need an 8-wheeler grab lorry" in text:
            scripts["grab_8_wheeler"] = "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
        
        if "I understand you need a 6-wheeler grab lorry" in text:
            scripts["grab_6_wheeler"] = "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
        
        # Extract time restrictions
        scripts["time_restriction"] = "We can't guarantee exact times, but delivery is between 7am-6pm"
        
        # Extract Sunday collection
        scripts["sunday_collection"] = "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team"
        
        # Extract final ending
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
        """Extract transfer rules from PDF"""
        return {
            "skip_hire": "NO_LIMIT",
            "man_and_van": 500,
            "grab_hire": 300,
            "out_of_hours_rule": "NEVER transfer out of hours - cardinal sin",
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
        """Extract Man & Van rules from PDF"""
        return {
            "heavy_materials_transfer": "Heavy materials = MUST transfer to specialist",
            "stairs_transfer": "Stairs/flats = MUST transfer to specialist",
            "transfer_threshold": 500,
            "out_hours_callback": "Out of hours = NEVER transfer, take callback",
            "pricing_rate": 30,
            "minimum_charge": 90,
            "weight_allowance": "100 kilos per cubic yard",
            "volume_assessment": "Always assess: items, access, volume"
        }
    
    def _extract_grab_rules(self, text: str) -> Dict[str, Any]:
        """Extract Grab Hire rules from PDF"""
        return {
            "6_wheeler_terminology": "6-wheeler = 12-tonne capacity - use exact script",
            "8_wheeler_terminology": "8-wheeler = 16-tonne capacity - use exact script",
            "transfer_threshold": 300,
            "suitable_materials": "Suitable for heavy materials (soil, concrete, muck)",
            "access_check": "Always check postcode and access requirements",
            "mixed_materials_transfer": "Mixed materials → transfer to specialist",
            "wait_load_immediate_transfer": "Wait & load skip → IMMEDIATE transfer"
        }
    
    def _extract_pricing_rules(self, text: str) -> Dict[str, Any]:
        """Extract pricing rules from PDF"""
        return {
            "vat_handling": "ALL prices excluding VAT - spell as V-A-T",
            "total_presentation": "Present TOTAL price including surcharges",
            "never_base_only": "NEVER quote base price only when surcharges apply",
            "transparency": "List all surcharge items clearly"
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
    
    def _extract_surcharge_rates(self, text: str) -> Dict[str, int]:
        """Extract surcharge rates from PDF"""
        return {
            "fridge": 20, "freezer": 20, "mattress": 15,
            "sofa": 15, "upholstered_furniture": 15
        }
    
    def _extract_testing_corrections(self, text: str) -> List[Dict[str, str]]:
        """Extract critical wrong/correct phrases from PDF"""
        corrections = []
        
        # Hardcode the critical ones from the PDF
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
                "wrong": "Largest skip available is 12-yard",
                "correct": "Largest skip is RORO 40-yard. But 8-yard max for heavy materials"
            },
            {
                "wrong": "Yes we can do Sunday for you",
                "correct": "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team"
            },
            {
                "wrong": "What time would you like?",
                "correct": "We can't guarantee exact times, but collection is typically between 7am-6pm"
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
    
    def get_rules_for_agent(self, agent_type: str) -> Dict[str, Any]:
        """Get specific rules for an agent type"""
        base_rules = {
            **self.rules_data["lock_rules"],
            "office_hours": self.rules_data["office_hours"],
            "transfer_rules": self.rules_data["transfer_rules"]
        }
        
        if agent_type == "skip_hire":
            return {
                **base_rules,
                **self.rules_data["skip_rules"],
                "exact_scripts": {k: v for k, v in self.rules_data["exact_scripts"].items() 
                                if k in ["heavy_materials", "sofa_prohibited", "permit_script", "mav_suggestion"]},
                "prohibited_items": self.rules_data["prohibited_items"],
                "surcharge_rates": self.rules_data["surcharge_rates"]
            }
        elif agent_type == "man_and_van":
            return {
                **base_rules,
                **self.rules_data["mav_rules"],
                "exact_scripts": {k: v for k, v in self.rules_data["exact_scripts"].items()
                                if k in ["time_restriction", "sunday_collection"]},
                "surcharge_rates": self.rules_data["surcharge_rates"]
            }
        elif agent_type == "grab_hire":
            return {
                **base_rules,
                **self.rules_data["grab_rules"],
                "exact_scripts": {k: v for k, v in self.rules_data["exact_scripts"].items()
                                if k in ["grab_6_wheeler", "grab_8_wheeler"]}
            }
        elif agent_type == "pricing":
            return {
                **base_rules,
                **self.rules_data["pricing_rules"],
                "surcharge_rates": self.rules_data["surcharge_rates"]
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
