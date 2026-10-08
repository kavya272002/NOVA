"""Reference lists and role definitions (the 'dropdown' sheet in the Google build)."""

REGIONS = ["Delhi NCR", "Mumbai", "Bangalore", "Hyderabad", "Chennai"]

ROLE_EXEC = "Regional Marketing Executive"
ROLE_RM = "Regional Manager"
ROLE_MM = "Marketing Manager"
ROLE_MH = "Marketing Head"
ROLE_BH = "Business Head"
ROLE_EXECUTION = "Execution Team"
ROLE_SYSTEM = "System"

APPROVER_ROLES = [ROLE_RM, ROLE_MM, ROLE_MH, ROLE_BH]
ALL_ROLES = [ROLE_EXEC, ROLE_RM, ROLE_MM, ROLE_MH, ROLE_BH, ROLE_EXECUTION]
MANAGEMENT_ROLES = [ROLE_MH, ROLE_BH]

# Friendly labels used on the Governance Check card
ROLE_APPROVAL_LABEL = {
    ROLE_RM: "Regional Manager Approval",
    ROLE_MM: "Marketing Manager Approval",
    ROLE_MH: "Marketing Head Approval",
    ROLE_BH: "Business Head Approval",
}

CAMPAIGN_TYPES = ["Product Launch", "Festive Promotion", "Lead Generation", "Brand Awareness",
                  "Retention & Loyalty", "Seasonal Sale", "Influencer Collaboration", "Retail Activation"]
OBJECTIVES = ["Lead Generation", "Brand Awareness", "Sales Conversion", "Customer Retention", "Market Expansion"]
CHANNELS = ["Instagram", "Google Ads", "Facebook", "YouTube", "WhatsApp Business", "Email",
            "Influencer", "Outdoor / OOH", "Retail In-store"]
PRODUCTS = ["NovaGlow Skincare", "FreshNest Home Care", "CrunchBay Snacks", "AquaPure Water Purifiers",
            "Voltix Smart Appliances", "KidoJoy Baby Care", "Brewlane Tea & Coffee", "StrideX Footwear"]
SEGMENTS = ["Young Professionals", "Urban Families", "College Students", "Premium Households",
            "Value Seekers", "New Parents", "Senior Citizens"]
LEAD_STATUSES = ["New", "Contacted", "Qualified", "Converted", "Lost"]
CONVERSION_STATUSES = ["Converted", "In Progress", "Not Converted"]

# Approval status (the governance field)
ST_DRAFT = "Draft"
ST_VALFAIL = "Validation Failed"
ST_PENDING = "Pending Approval"
ST_APPROVED = "Fully Approved"
ST_REJECTED = "Rejected"
ST_REWORK = "Rework Required"
APPROVAL_STATUSES = [ST_DRAFT, ST_VALFAIL, ST_PENDING, ST_APPROVED, ST_REJECTED, ST_REWORK]
EDITABLE_STATUSES = [ST_DRAFT, ST_VALFAIL, ST_REJECTED, ST_REWORK]

# Execution status
EX_NOT_READY = "Not Ready"
EX_READY = "Ready for Execution"
EX_DONE = "Executed"
EXECUTION_STATUSES = [EX_NOT_READY, EX_READY, EX_DONE]

# Derived pipeline stage (used for the 'Campaign Status' filter and Chart 6)
PIPELINE = ["Draft", "Pending Approval", "Approved", "Ready for Execution", "Executed"]
