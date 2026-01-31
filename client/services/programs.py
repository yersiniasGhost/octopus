"""
Hardcoded program data and constants for Energy Conservation Client Portal.

Contains Ohio-specific energy programs, opportunity categories, FPL tables,
and savings estimates for various improvements.
"""

# Supported counties
COUNTIES = ["Franklin", "Cuyahoga"]

# Federal Poverty Level 2024 (for eligibility calculations)
# Add $5,380 for each additional person beyond 8
FPL_2024 = {
    1: 15060,
    2: 20440,
    3: 25820,
    4: 31200,
    5: 36580,
    6: 41960,
    7: 47340,
    8: 52720
}
FPL_ADDITIONAL_PERSON = 5380


def get_fpl_limit(household_size: int, percentage: int = 100) -> float:
    """Calculate FPL limit for a given household size and percentage."""
    if household_size <= 0:
        household_size = 1
    if household_size <= 8:
        base = FPL_2024[household_size]
    else:
        base = FPL_2024[8] + (household_size - 8) * FPL_ADDITIONAL_PERSON
    return base * (percentage / 100)


# Energy assistance programs (Ohio-specific)
ENERGY_PROGRAMS = [
    {
        "id": "heap",
        "name": "HEAP",
        "full_name": "Home Energy Assistance Program",
        "description": "Helps eligible low-income households pay heating and cooling bills",
        "income_limit_pct_fpl": 175,
        "benefits": [
            "Winter heating assistance (up to $800)",
            "Summer cooling assistance (up to $500)",
            "Year-round emergency assistance"
        ],
        "how_to_apply": "Contact your local Community Action Agency",
        "website": "https://energyhelp.ohio.gov"
    },
    {
        "id": "wap",
        "name": "WAP",
        "full_name": "Weatherization Assistance Program",
        "description": "Provides free home weatherization services for income-eligible households",
        "income_limit_pct_fpl": 200,
        "benefits": [
            "Free energy audit",
            "Attic and wall insulation",
            "Air sealing",
            "Heating system repair or replacement",
            "Health and safety improvements"
        ],
        "how_to_apply": "Contact your local Community Action Agency",
        "website": "https://energyhelp.ohio.gov"
    },
    {
        "id": "utility_rebates",
        "name": "Utility Rebates",
        "full_name": "AEP Ohio / Columbia Gas Rebate Programs",
        "description": "Rebates for energy-efficient equipment upgrades",
        "income_limit_pct_fpl": None,
        "benefits": [
            "Smart thermostat rebate ($50-100)",
            "HVAC tune-up rebate ($50)",
            "Heat pump rebates (up to $500)",
            "Insulation rebates"
        ],
        "how_to_apply": "Visit your utility company's website",
        "website": "https://www.aepohio.com/savings"
    },
    {
        "id": "federal_tax_credits",
        "name": "Federal Tax Credits",
        "full_name": "Energy Efficient Home Improvement Credit",
        "description": "Federal tax credits for qualifying home energy improvements",
        "income_limit_pct_fpl": None,
        "benefits": [
            "30% credit for heat pumps (up to $2,000/year)",
            "30% credit for insulation, windows, doors (up to $1,200/year)",
            "30% credit for electrical panel upgrades (up to $600)",
            "30% credit for home energy audits (up to $150)"
        ],
        "how_to_apply": "Claim on federal tax return (Form 5695)",
        "website": "https://www.energystar.gov/about/federal_tax_credits"
    },
    {
        "id": "led_program",
        "name": "LED Lighting Program",
        "full_name": "Utility LED Bulb Program",
        "description": "Free or discounted LED bulbs for utility customers",
        "income_limit_pct_fpl": None,
        "benefits": [
            "Free LED bulbs (varies by program)",
            "Discounted smart LED bulbs",
            "In-store instant rebates at participating retailers"
        ],
        "how_to_apply": "Check utility website or visit participating retailers",
        "website": "https://www.aepohio.com/savings"
    }
]

# Opportunity categories with display properties
OPPORTUNITY_CATEGORIES = {
    "weatherization": {
        "icon": "fa-house-chimney",
        "label": "Weatherization",
        "color": "#4CAF50",
        "emoji": "🏠"
    },
    "hvac": {
        "icon": "fa-temperature-half",
        "label": "HVAC",
        "color": "#2196F3",
        "emoji": "❄️"
    },
    "appliances": {
        "icon": "fa-lightbulb",
        "label": "Appliances & Lighting",
        "color": "#FF9800",
        "emoji": "💡"
    },
    "behavioral": {
        "icon": "fa-plug",
        "label": "Behavioral Changes",
        "color": "#9C27B0",
        "emoji": "🔌"
    },
    "programs": {
        "icon": "fa-dollar-sign",
        "label": "Programs & Rebates",
        "color": "#F44336",
        "emoji": "💰"
    }
}

# Savings estimates for various improvements (percentages of annual energy cost)
SAVINGS_ESTIMATES = {
    "attic_insulation": {
        "pct_low": 10, "pct_high": 20,
        "cost_low": 1500, "cost_high": 3000,
        "description": "Adding or upgrading attic insulation"
    },
    "wall_insulation": {
        "pct_low": 10, "pct_high": 15,
        "cost_low": 3000, "cost_high": 8000,
        "description": "Adding wall cavity insulation"
    },
    "air_sealing": {
        "pct_low": 5, "pct_high": 15,
        "cost_low": 300, "cost_high": 1000,
        "description": "Sealing air leaks around windows, doors, and penetrations"
    },
    "window_replacement": {
        "pct_low": 7, "pct_high": 15,
        "cost_low": 8000, "cost_high": 20000,
        "description": "Replacing old windows with energy-efficient models"
    },
    "hvac_upgrade": {
        "pct_low": 15, "pct_high": 30,
        "cost_low": 5000, "cost_high": 15000,
        "description": "Upgrading to high-efficiency HVAC system"
    },
    "hvac_maintenance": {
        "pct_low": 5, "pct_high": 10,
        "cost_low": 100, "cost_high": 300,
        "description": "Regular HVAC maintenance and tune-up"
    },
    "smart_thermostat": {
        "pct_low": 8, "pct_high": 12,
        "cost_low": 150, "cost_high": 300,
        "description": "Installing a programmable or smart thermostat"
    },
    "water_heater": {
        "pct_low": 5, "pct_high": 15,
        "cost_low": 1000, "cost_high": 3000,
        "description": "Upgrading to high-efficiency water heater"
    },
    "led_lighting": {
        "pct_low": 2, "pct_high": 5,
        "cost_low": 50, "cost_high": 200,
        "description": "Replacing incandescent bulbs with LEDs"
    },
    "energy_star_appliances": {
        "pct_low": 3, "pct_high": 10,
        "cost_low": 500, "cost_high": 3000,
        "description": "Replacing old appliances with ENERGY STAR models"
    }
}


def calculate_savings_estimate(improvement_type: str, annual_energy_cost: float) -> dict:
    """
    Calculate estimated savings for a specific improvement.

    Returns dict with low/high savings estimates and implementation cost range.
    """
    if improvement_type not in SAVINGS_ESTIMATES:
        return {"error": f"Unknown improvement type: {improvement_type}"}

    est = SAVINGS_ESTIMATES[improvement_type]
    savings_low = annual_energy_cost * (est["pct_low"] / 100)
    savings_high = annual_energy_cost * (est["pct_high"] / 100)

    return {
        "improvement_type": improvement_type,
        "description": est["description"],
        "annual_savings_low": round(savings_low, 2),
        "annual_savings_high": round(savings_high, 2),
        "savings_range": f"${int(savings_low)}-${int(savings_high)}/yr",
        "implementation_cost_low": est["cost_low"],
        "implementation_cost_high": est["cost_high"],
        "cost_range": f"${est['cost_low']:,}-${est['cost_high']:,}",
        "simple_payback_years_low": round(est["cost_low"] / savings_high, 1) if savings_high > 0 else None,
        "simple_payback_years_high": round(est["cost_high"] / savings_low, 1) if savings_low > 0 else None
    }


def get_eligible_programs(annual_income: float, household_size: int) -> list:
    """
    Get list of programs the household may be eligible for.

    Returns programs with eligibility status.
    """
    eligible = []

    for program in ENERGY_PROGRAMS:
        program_info = program.copy()

        if program["income_limit_pct_fpl"] is None:
            # No income limit - available to all
            program_info["eligible"] = True
            program_info["eligibility_note"] = "Available to all customers"
        else:
            limit = get_fpl_limit(household_size, program["income_limit_pct_fpl"])
            program_info["income_limit"] = limit
            program_info["eligible"] = annual_income <= limit

            if program_info["eligible"]:
                program_info["eligibility_note"] = f"Income under {program['income_limit_pct_fpl']}% FPL"
            else:
                over_by = annual_income - limit
                program_info["eligibility_note"] = f"Income ${over_by:,.0f} over limit"

        eligible.append(program_info)

    return eligible
