from app.core.config import settings
from app.services.classifier.protocol import ClassifierProtocol


def get_classifier(name: str | None = None) -> ClassifierProtocol:
    """
    Registry-based factory. Phase 2 adds 'llama-1b-v1' entry here only.
    No other pipeline code changes when Phase 2 classifier is introduced.
    Pipeline code must only import get_classifier, never RuleBasedClassifier.
    """
    from app.services.classifier.rule_based import RuleBasedClassifier  # local import avoids cycles

    classifier_name = name or settings.classifier_name
    registry: dict[str, type] = {
        "rule-based-v1": RuleBasedClassifier,
        # Phase 2: "llama-1b-v1": NIMClassifier,
    }
    if classifier_name not in registry:
        raise ValueError(f"Unknown classifier: {classifier_name!r}")
    return registry[classifier_name]()
