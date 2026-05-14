# Energy Conservation Client Portal - Implementation Brief

**Created**: 2026-01-31
**Status**: Ready for Implementation
**Location**: `/client/` (separate Flask application)

---

## Executive Summary

Build a single-page Flask demo application that displays user energy data with an AI-powered conservation advisor. Users search for residents by name, view their energy profile and comparables, and interact with an AI chatbot that identifies energy-saving opportunities.

---

## Technical Specifications

### Stack
- **Backend**: Flask (Python 3.x)
- **Database**: MongoDB (existing `empower_development` database)
- **AI**: Claude API (Anthropic) with tool use
- **Frontend**: HTML5, Bootstrap 5 (dark theme), Chart.js, vanilla JavaScript
- **No Authentication**: Demo only

### Directory Structure
```
client/
├── app.py                      # Flask entry point & routes
├── config.py                   # Configuration (MongoDB URI, Claude API key)
├── requirements.txt            # Dependencies
├── static/
│   ├── css/
│   │   └── style.css           # Dark theme styles
│   └── js/
│       └── main.js             # Frontend logic, charts, chat
├── templates/
│   └── index.html              # Single-page template
└── services/
    ├── __init__.py
    ├── mongo_service.py        # MongoDB data access layer
    ├── advisor_service.py      # Claude AI advisor with tools
    └── programs.py             # Hardcoded program data
```

---

## Data Model

### Source Collections (MongoDB: `empower_development`)

**Demographic Data**: `{County}CountyDemographic`
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Primary key |
| `parcel_id` | string | Links to residential data |
| `customer_name` | string | Searchable name field |
| `address` | string | Property address |
| `estimated_income` | number | Annual household income |
| `household_size` | number | Number of people |
| `annual_kwh_cost` | number | Annual electricity cost |
| `annual_gas_cost` | number | Annual gas cost |
| `energy_burden_kwh` | number | Energy burden percentage |

**Residential Data**: `{County}CountyResidential`
| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | Primary key |
| `parcel_id` | string | Links to demographic data |
| `living_area_sqft` | number | Home square footage |
| `story_height` | number | Number of stories |
| `age` | number | Home age in years |
| `bedrooms` | number | Bedroom count |
| `bathrooms` | number | Bathroom count |
| `energy_percentile.percentile_rank` | number | 0-100 percentile vs similar homes |

**Campaign Participants**: `participants` (in `campaign_data` database)
| Field | Type | Description |
|-------|------|-------------|
| `parcel_id` | string | Links to demographic/residential |

### Hardcoded Counties
```python
COUNTIES = ["Franklin", "Cuyahoga"]
```

---

## API Endpoints

### GET `/`
Main page - serves `index.html`

### GET `/api/counties`
Returns list of available counties.
```json
{
  "success": true,
  "counties": ["Franklin", "Cuyahoga"]
}
```

### POST `/api/search`
Search users by name with filters.

**Request:**
```json
{
  "query": "John Smith",
  "county": "Franklin",
  "participants_only": false
}
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "id": "parcel_id_123",
      "name": "John Smith",
      "address": "123 Main St, Columbus OH",
      "county": "Franklin"
    }
  ],
  "count": 1
}
```

### GET `/api/user/<parcel_id>?county=Franklin`
Get full user profile with comparables.

**Response:**
```json
{
  "success": true,
  "profile": {
    "parcel_id": "parcel_id_123",
    "name": "John Smith",
    "address": "123 Main St, Columbus OH",
    "county": "Franklin",
    "demographic": {
      "estimated_income": 52000,
      "household_size": 4,
      "annual_kwh_cost": 1842,
      "annual_gas_cost": 1156,
      "total_energy_cost": 2998,
      "energy_burden_pct": 5.8
    },
    "home": {
      "living_area_sqft": 1850,
      "story_height": 2,
      "age": 42,
      "bedrooms": 3,
      "bathrooms": 2
    },
    "energy_percentile": 78,
    "comparables": {
      "count": 25,
      "avg_total_cost": 2340,
      "median_total_cost": 2280,
      "potential_savings": 658
    }
  }
}
```

### POST `/api/chat`
Send message to AI advisor.

**Request:**
```json
{
  "message": "Yes, I do notice cold spots near the windows",
  "user_context": {
    "parcel_id": "parcel_id_123",
    "county": "Franklin"
  },
  "conversation_history": []
}
```

**Response:**
```json
{
  "success": true,
  "response": "Cold spots near windows often indicate air leaks...",
  "opportunities_added": [
    {
      "category": "weatherization",
      "description": "Seal air leaks around windows",
      "estimated_savings": "$50-150/yr",
      "priority": "high"
    }
  ],
  "conversation_history": [...]
}
```

### GET/POST/DELETE `/api/opportunities`
Manage session opportunities list (stored in frontend, passed to API).

---

## AI Advisor Design

### System Prompt
```
You are an Energy Conservation Advisor helping homeowners identify opportunities
to reduce energy consumption and costs. You have access to the user's energy data,
home characteristics, and comparable analysis.

CURRENT USER CONTEXT:
{user_profile_json}

KEY OBSERVATIONS:
- Energy Percentile: {percentile}th (uses more energy than {percentile}% of similar homes)
- Annual Energy Cost: ${total_cost}
- Comparable Homes Average: ${comparable_avg}
- Potential Savings: ${savings} if reduced to median

YOUR APPROACH:
1. Start by acknowledging what you see in their data
2. Ask ONE focused question at a time to identify opportunities
3. Listen to their responses and probe deeper when relevant
4. Use the add_opportunity tool when you identify a concrete opportunity
5. Recommend programs when the user appears eligible
6. Suggest contractor types (generically) for improvements requiring professional help

QUESTION AREAS TO EXPLORE:
- Comfort issues (cold spots, drafts, rooms that don't heat/cool well)
- HVAC system (age, maintenance, thermostat habits)
- Insulation awareness (attic, walls, basement)
- Windows and doors (age, condition, weatherstripping)
- Appliances (age of water heater, fridge, washer/dryer)
- Lighting (still using incandescent bulbs?)
- Behavioral habits (thermostat settings, phantom loads)

CONVERSATION STYLE:
- Warm, helpful, non-judgmental
- Explain WHY each recommendation matters
- Prioritize high-impact, low-cost opportunities first
- Be specific with savings estimates when possible
- Keep responses concise (2-3 paragraphs max)

WHEN RECOMMENDING PROGRAMS:
- HEAP: For households with income <175% federal poverty level
- WAP: For households with income <200% federal poverty level
- Utility Rebates: Available to all customers
- Federal Tax Credits: Available to all homeowners
- LED Program: Available to all utility customers

WHEN SUGGESTING CONTRACTORS:
- Use generic terms: "HVAC contractor", "insulation contractor", "weatherization specialist"
- Recommend getting multiple quotes
- Mention that WAP provides free services for eligible households
```

### AI Tools

#### Tool 1: `get_user_profile`
```python
{
    "name": "get_user_profile",
    "description": "Retrieve the current user's complete energy and demographic profile",
    "input_schema": {
        "type": "object",
        "properties": {
            "parcel_id": {
                "type": "string",
                "description": "The user's parcel ID"
            },
            "county": {
                "type": "string",
                "description": "The county name"
            }
        },
        "required": ["parcel_id", "county"]
    }
}
```

#### Tool 2: `get_comparables`
```python
{
    "name": "get_comparables",
    "description": "Get energy data for comparable homes (similar size, age, characteristics)",
    "input_schema": {
        "type": "object",
        "properties": {
            "parcel_id": {
                "type": "string",
                "description": "The user's parcel ID"
            },
            "county": {
                "type": "string",
                "description": "The county name"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of comparables to return",
                "default": 10
            }
        },
        "required": ["parcel_id", "county"]
    }
}
```

#### Tool 3: `calculate_savings`
```python
{
    "name": "calculate_savings",
    "description": "Estimate potential savings for a specific energy improvement",
    "input_schema": {
        "type": "object",
        "properties": {
            "improvement_type": {
                "type": "string",
                "enum": [
                    "attic_insulation",
                    "wall_insulation",
                    "air_sealing",
                    "window_replacement",
                    "hvac_upgrade",
                    "hvac_maintenance",
                    "smart_thermostat",
                    "water_heater",
                    "led_lighting",
                    "energy_star_appliances"
                ],
                "description": "Type of improvement"
            },
            "current_annual_cost": {
                "type": "number",
                "description": "User's current annual energy cost"
            },
            "home_age": {
                "type": "integer",
                "description": "Age of the home in years"
            },
            "home_sqft": {
                "type": "integer",
                "description": "Home square footage"
            }
        },
        "required": ["improvement_type", "current_annual_cost"]
    }
}
```

**Savings Estimates (hardcoded ranges):**
```python
SAVINGS_ESTIMATES = {
    "attic_insulation": {"pct_low": 10, "pct_high": 20, "cost_low": 1500, "cost_high": 3000},
    "wall_insulation": {"pct_low": 10, "pct_high": 15, "cost_low": 3000, "cost_high": 8000},
    "air_sealing": {"pct_low": 5, "pct_high": 15, "cost_low": 300, "cost_high": 1000},
    "window_replacement": {"pct_low": 7, "pct_high": 15, "cost_low": 8000, "cost_high": 20000},
    "hvac_upgrade": {"pct_low": 15, "pct_high": 30, "cost_low": 5000, "cost_high": 15000},
    "hvac_maintenance": {"pct_low": 5, "pct_high": 10, "cost_low": 100, "cost_high": 300},
    "smart_thermostat": {"pct_low": 8, "pct_high": 12, "cost_low": 150, "cost_high": 300},
    "water_heater": {"pct_low": 5, "pct_high": 15, "cost_low": 1000, "cost_high": 3000},
    "led_lighting": {"pct_low": 2, "pct_high": 5, "cost_low": 50, "cost_high": 200},
    "energy_star_appliances": {"pct_low": 3, "pct_high": 10, "cost_low": 500, "cost_high": 3000}
}
```

#### Tool 4: `lookup_programs`
```python
{
    "name": "lookup_programs",
    "description": "Find energy assistance programs the user may be eligible for",
    "input_schema": {
        "type": "object",
        "properties": {
            "annual_income": {
                "type": "number",
                "description": "Household annual income"
            },
            "household_size": {
                "type": "integer",
                "description": "Number of people in household"
            }
        },
        "required": ["annual_income", "household_size"]
    }
}
```

**Federal Poverty Level 2024 (for eligibility calculation):**
```python
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
# Add $5,380 for each additional person
```

#### Tool 5: `add_opportunity`
```python
{
    "name": "add_opportunity",
    "description": "Add an identified energy-saving opportunity to the user's checklist",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": ["weatherization", "hvac", "appliances", "behavioral", "programs"],
                "description": "Category of the opportunity"
            },
            "description": {
                "type": "string",
                "description": "Brief description of the opportunity (e.g., 'Seal air leaks around windows')"
            },
            "estimated_savings": {
                "type": "string",
                "description": "Estimated annual savings range (e.g., '$50-150/yr')"
            },
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Priority based on impact and ease of implementation"
            },
            "contractor_type": {
                "type": "string",
                "description": "Type of contractor needed, if applicable (e.g., 'HVAC contractor')"
            },
            "program_name": {
                "type": "string",
                "description": "Related assistance program, if applicable (e.g., 'WAP')"
            }
        },
        "required": ["category", "description", "priority"]
    }
}
```

---

## Hardcoded Data

### Programs
```python
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
```

### Opportunity Categories
```python
OPPORTUNITY_CATEGORIES = {
    "weatherization": {
        "icon": "🏠",
        "label": "Weatherization",
        "color": "#4CAF50"
    },
    "hvac": {
        "icon": "❄️",
        "label": "HVAC",
        "color": "#2196F3"
    },
    "appliances": {
        "icon": "💡",
        "label": "Appliances & Lighting",
        "color": "#FF9800"
    },
    "behavioral": {
        "icon": "🔌",
        "label": "Behavioral Changes",
        "color": "#9C27B0"
    },
    "programs": {
        "icon": "💰",
        "label": "Programs & Rebates",
        "color": "#F44336"
    }
}
```

---

## UI Specifications

### Color Scheme (Dark Theme)
```css
:root {
    --bg-primary: #1a1a2e;
    --bg-secondary: #16213e;
    --bg-card: #1f2940;
    --text-primary: #eaeaea;
    --text-secondary: #a0a0a0;
    --accent-primary: #4ecca3;
    --accent-secondary: #00d9ff;
    --warning: #ff6b6b;
    --success: #4ecca3;
    --border: #2d3748;
}
```

### Chart Specifications

#### 1. Energy Percentile Gauge
- **Type**: Doughnut chart (180° half-circle)
- **Data**: Single value (percentile rank)
- **Colors**: Gradient from green (0-30) → yellow (30-70) → red (70-100)
- **Center Text**: "{percentile}th percentile"
- **Label Below**: "You use more energy than {percentile}% of similar homes"

#### 2. Cost Comparison Bar Chart
- **Type**: Horizontal bar chart
- **Bars**:
  - Your Electric Cost vs Comparable Avg Electric
  - Your Gas Cost vs Comparable Avg Gas
  - Your Total vs Comparable Avg Total
- **Colors**: User = accent color, Comparable = muted gray
- **Labels**: Show dollar values on bars

#### 3. Savings Potential Display
- **Type**: Metric card (not a chart)
- **Content**: "If you reduced to median: Save ${amount}/year"
- **Style**: Large number, accent color, subtle animation

### Layout Grid
```
Desktop (>1200px):
┌─────────────────────────────────────────────────────────────┐
│                         HEADER                              │
├──────────────┬──────────────────────────────────────────────┤
│   Profile    │              Chat + Opportunities            │
│   (350px)    │              (flex: 1)                       │
│              │  ┌─────────────────┬─────────────────────┐   │
│              │  │     Chat        │   Opportunities     │   │
│              │  │     (65%)       │   (35%)             │   │
│              │  └─────────────────┴─────────────────────┘   │
└──────────────┴──────────────────────────────────────────────┘

Tablet (768-1200px):
┌─────────────────────────────────────────────────────────────┐
│                         HEADER                              │
├─────────────────────────────────────────────────────────────┤
│                        Profile                              │
├─────────────────────────────────────────────────────────────┤
│           Chat              │        Opportunities          │
└─────────────────────────────────────────────────────────────┘

Mobile (<768px):
┌──────────────────────┐
│       HEADER         │
├──────────────────────┤
│      Profile         │
├──────────────────────┤
│       Chat           │
├──────────────────────┤
│   Opportunities      │
└──────────────────────┘
```

---

## Implementation Phases

### Phase 1: Foundation
- [ ] Set up Flask app structure in `client/`
- [ ] Create `config.py` with MongoDB and Claude API configuration
- [ ] Implement `mongo_service.py` with data access methods
- [ ] Create basic `index.html` template with dark theme

### Phase 2: Search & Profile
- [ ] Implement county selector and participant checkbox
- [ ] Build user search functionality
- [ ] Create profile display component
- [ ] Implement Chart.js visualizations

### Phase 3: AI Advisor
- [ ] Set up Claude API integration in `advisor_service.py`
- [ ] Implement all 5 AI tools
- [ ] Create chat interface component
- [ ] Build conversation flow with tool handling

### Phase 4: Opportunities
- [ ] Create opportunities sidebar component
- [ ] Implement add/remove functionality
- [ ] Connect AI tool to opportunities list
- [ ] Add category grouping and icons

### Phase 5: Polish
- [ ] Responsive design adjustments
- [ ] Loading states and error handling
- [ ] Final styling and animations
- [ ] Testing with real data

---

## Dependencies

### requirements.txt
```
flask>=3.0.0
pymongo>=4.0.0
anthropic>=0.39.0
python-dotenv>=1.0.0
```

### Frontend (CDN)
- Bootstrap 5.3.x (dark theme)
- Chart.js 4.x
- Font Awesome 6.x (icons)

---

## Environment Variables
```
MONGODB_URI=mongodb://localhost:27017
MONGODB_EMPOWER_DB=empower_development
MONGODB_CAMPAIGN_DB=campaign_data
ANTHROPIC_API_KEY=sk-ant-...
FLASK_SECRET_KEY=your-secret-key
FLASK_DEBUG=true
```

---

## Notes & Considerations

1. **No Auth**: This is a demo - anyone with access can search any user
2. **Session-Only Opportunities**: Opportunities list resets on page refresh
3. **No Chat Persistence**: Conversation history is not saved to database
4. **Hardcoded Programs**: Ohio-specific programs; update for other regions
5. **Generic Contractors**: No specific contractor recommendations

---

## Future Enhancements (Out of Scope for Demo)

- User authentication and personal dashboards
- Persistent conversation history
- Program application integration
- Contractor directory with ratings
- Email report generation
- Mobile app version
