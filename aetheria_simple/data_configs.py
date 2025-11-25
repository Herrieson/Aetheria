"""Dataset configuration presets for the simplified pipeline."""

from __future__ import annotations

USB_ONLY_IMAGE_RELABELED_DATASET_CONFIG = {
    "input_1": "description",
    "input_2": None,
    "label_field": "voted_img_risk",
    # "label_field": "img_risk",
    "label_mapping": {
        "1": 1,
        "0": 0,
    },
    "prompt_profile": "image_only",
    "rag_collection": "safety_cases_image",
}

USB_TEXT_IMG_RELABELED_DATASET_CONFIG = {
    "input_1": "text",
    "input_2": "description",
    "label_field": "voted_risk",
    "label_mapping": {
        "1": 1,
        "0": 0,
    },
    "prompt_profile": "default",
    "rag_collection": "safety_cases_default",
    # "rag_collection": "safety_cases_meta_5",
}

ONLY_TEXT_DATASET_CONFIG = {
    "input_1": "input",
    "input_2": None,
    "label_field": "label",
    "label_mapping": {
        "harmful": 1,
        "unharmful": 0,
    },
    "prompt_profile": "text_only",
    "rag_collection": "safety_cases_text",
}


__all__ = [
    "USB_ONLY_IMAGE_RELABELED_DATASET_CONFIG",
    "USB_TEXT_IMG_RELABELED_DATASET_CONFIG",
    "ONLY_TEXT_DATASET_CONFIG",
]
