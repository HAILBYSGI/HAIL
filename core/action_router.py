# action_router.py
# Routes classified user intent to the appropriate HAIL execution module

from intent_classifier import IntentClassifier
from modules import (
    AutoAmanahEngine,
    IbadahTracker,
    DuaResponseEngine,
    ZakatModule,
    HalalInvestmentSystem,
    FamilyAlignmentCore,
    IslamicWorkflowEngine,
    QuranTherapyModule,
    HalalCompanion,
    WellnessMonitor
)

class ActionRouter:
    def __init__(self):
        self.classifier = IntentClassifier()

        # Initialize system modules
        self.modules = {
            "Auto-Amanah Engine": AutoAmanahEngine(),
            "Ibadah Tracker": IbadahTracker(),
            "Dua Response Engine": DuaResponseEngine(),
            "Zakat Module": ZakatModule(),
            "Halal Investment System": HalalInvestmentSystem(),
            "Family Alignment Core": FamilyAlignmentCore(),
            "Islamic Workflow Engine": IslamicWorkflowEngine(),
            "Qur’an-Based Therapy": QuranTherapyModule(),
            "Daily Halal Companion": HalalCompanion(),
            "Wellness Monitor": WellnessMonitor()
        }

    def handle_request(self, user_input):
        module_name = self.classifier.classify(user_input)
        if module_name in self.modules:
            return self.modules[module_name].execute(user_input)
        else:
            return "System: Unable to route your request. Please clarify or specify your intent."
