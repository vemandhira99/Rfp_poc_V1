"""
company_profile.py
──────────────────
Company profile used across all generated documents.
Never outputs placeholders like [Your Company Name].
Update these values to match the actual organization.
"""

COMPANY_PROFILE = {
    "company_legal_name": "DHIRA Software Labs Pvt. Ltd.",
    "brand_name": "DHIRA",
    "product_name": "Akashic Unified Data Platform",
    "platform_short_name": "Akashic",
    "website": "https://www.dhira.in",
    "email": "proposals@dhira.in",
    "address": "India",
    "authorized_signatory": "Authorized Signatory, DHIRA Software Labs Pvt. Ltd.",
    "footer_text": "©2025 DHIRA Software Labs Pvt. Ltd. Confidential and Proprietary",
    "confidentiality_text": (
        "This document is confidential and proprietary to DHIRA Software Labs Pvt. Ltd. "
        "It is submitted in response to a formal Request for Proposal and is intended solely "
        "for the use of the recipient organization. Any reproduction or distribution without "
        "written consent is strictly prohibited."
    ),
    "company_overview": (
        "DHIRA Software Labs Pvt. Ltd. is an enterprise technology company specializing in "
        "intelligent data platforms, AI-driven automation, and digital transformation solutions. "
        "Our flagship product, Akashic Unified Data Platform, enables government and enterprise "
        "organizations to unify, analyze, and act on complex data at scale."
    ),
    "platform_description": (
        "Akashic is a unified data platform built for large-scale government and enterprise deployments. "
        "It provides end-to-end capabilities including data ingestion, workflow automation, AI analytics, "
        "compliance management, and real-time reporting — all within a single secure and scalable architecture."
    ),
    "certifications": [
        "ISO 27001 Information Security Management",
        "CMMI Level 3 Appraised",
    ],
    "past_project_references": [
        "Enterprise Data Platform for Central Government Ministry",
        "State-level Workflow Automation — Education Sector",
        "AI-powered Analytics Dashboard for Public Sector",
    ],
    "standard_capability_statement": (
        "DHIRA Software Labs brings deep expertise in enterprise software architecture, cloud-native platforms, "
        "AI/ML integration, and large-scale government IT implementations. We deliver end-to-end solutions "
        "with proven implementation methodology and 24x7 support frameworks."
    ),
}


def get_company_profile() -> dict:
    """Returns the company profile dictionary."""
    return COMPANY_PROFILE


def company_name() -> str:
    return COMPANY_PROFILE["company_legal_name"]


def brand_name() -> str:
    return COMPANY_PROFILE["brand_name"]


def footer() -> str:
    return COMPANY_PROFILE["footer_text"]
