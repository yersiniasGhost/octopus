# Bayesian Model System - Architecture and Usage

**Created:** 2025-12-03
**Purpose:** Document the Bayesian model metadata system and model management architecture

## Overview

The Bayesian model system provides a standardized way to define, manage, and present statistical models in the UI. Models are auto-discovered from the `src/bayesian_models/` directory and presented in a dropdown for training and inference.

## Architecture Components

### 1. Base Model Class (`src/bayesian_models/base_model.py`)

Provides the foundation for all Bayesian models:

- **`BaseBayesianModel`**: Abstract base class that all models inherit from
- **`ModelMetadata`**: Loads and manages model configuration from `config.yaml`
- **`InferenceParameter`**: Defines parameter metadata for inference forms

**Key Methods:**
- `load_data()`: Load and prepare training data
- `train()`: Train the Bayesian model
- `predict()`: Run inference with trained model
- `get_inference_form_fields()`: Get form field definitions for UI
- `validate_inference_params()`: Validate user-provided parameters

### 2. Model Registry (`src/bayesian_models/model_registry.py`)

Auto-discovery and management system:

- **`ModelRegistry`**: Scans `src/bayesian_models/` for models with `config.yaml`
- **`get_registry()`**: Global singleton registry instance

**Key Methods:**
- `get_all_models()`: Returns all registered models
- `get_model_metadata(model_id)`: Get specific model metadata
- `load_model_instance(model_id)`: Dynamically load and instantiate model class
- `get_model_for_dropdown()`: Get (id, name) tuples for HTML dropdowns

### 3. Configuration Files (`config.yaml`)

Each model directory must contain a `config.yaml` with:

```yaml
name: "Display Name"
description: "Model description for UI"
version: "1.0"
author: "Your Name"
status: "active"  # active, beta, deprecated

tags:
  - "category1"
  - "category2"

inference_params:
  - name: "param_name"
    type: "integer"  # integer, float, string, select, boolean
    label: "Display Label"
    default: 100
    required: true
    min_value: 1
    max_value: 1000
    help_text: "Parameter description"
```

### 4. UI Integration

**Route:** `app/routes/main.py:modeling_dashboard()`
- Loads model registry
- Gets selected model from query params
- Passes model list and details to template

**Template:** `app/templates/dashboards/modeling.html`
- Dropdown for model selection
- Model details display (name, description, version, author, tags)
- Action buttons: "Train Model" and "Run Inference"
- Inference parameters table preview

## Directory Structure

```
src/bayesian_models/
├── base_model.py           # Base classes and metadata handling
├── model_registry.py       # Auto-discovery and management
├── click_model/            # Example model
│   ├── config.yaml         # Model metadata
│   ├── click_model.py      # Model implementation
│   ├── click_model_data.py # Data loading
│   └── ...
└── model02/                # Add more models here
    ├── config.yaml
    └── model.py
```

## How to Add a New Model

### Step 1: Create Model Directory

```bash
mkdir src/bayesian_models/my_new_model
```

### Step 2: Create `config.yaml`

```yaml
name: "My New Model"
description: "Brief description of what the model does"
version: "1.0"
author: "Your Name"
status: "active"

tags:
  - "conversion"
  - "hierarchical"

inference_params:
  - name: "county"
    type: "select"
    label: "County"
    required: true
    options:
      - "Cuyahoga"
      - "Franklin"
      - "Hamilton"

  - name: "sample_size"
    type: "integer"
    label: "Sample Size"
    default: 1000
    min_value: 100
    max_value: 10000
```

### Step 3: Create Model Implementation

Create `my_new_model/model.py`:

```python
from pathlib import Path
from typing import Any, Dict
from src.causal_models.base_model import BaseBayesianModel


class MyNewModel(BaseBayesianModel):
    """
    My new Bayesian model implementation
    """



    def __init__(self, model_dir: Path):
        super().__init__(model_dir)
        # Additional initialization



    def load_data(self, **kwargs) -> Any:
        """Load and prepare data"""
        # Implementation
        pass



    def train(self, data: Any, **kwargs) -> Dict[str, Any]:
        """Train the model"""
        # Implementation
        return {
            'status': 'success',
            'metrics': {...}
        }



    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference"""
        # Validate parameters
        is_valid, error = self.validate_inference_params(inference_params)
        if not is_valid:
            return {'error': error}

        # Run inference
        # Implementation
        return {
            'predictions': [...],
            'credible_intervals': {...}
        }
```

### Step 4: Verify Registration

The model will be auto-discovered on next dashboard load. To verify:

1. Navigate to `/dashboard/modeling`
2. Your model should appear in the dropdown
3. Select it to see details and action buttons

## Parameter Types

### Supported Types

- **`integer`**: Whole numbers with optional min/max validation
- **`float`**: Decimal numbers with optional min/max validation
- **`string`**: Text input
- **`select`**: Dropdown with predefined options
- **`boolean`**: Checkbox (true/false)

### Parameter Schema

```yaml
- name: "param_id"           # Internal parameter name
  type: "float"               # Parameter type
  label: "Display Label"      # UI label
  default: 0.95               # Default value
  required: true              # Whether parameter is required
  min_value: 0.0              # Minimum value (numeric types)
  max_value: 1.0              # Maximum value (numeric types)
  options: ["A", "B"]         # Options for select type
  help_text: "Description"    # Help text for users
```

## UI Workflow

1. **Select Model**: User chooses model from dropdown
2. **View Details**: Model name, description, version, author, tags displayed
3. **Choose Action**:
   - **Train Model**: Navigate to training interface
   - **Run Inference**: Navigate to inference form
4. **Inference Parameters**: Preview of required/optional parameters

## Model Status Flags

- **`active`**: Production-ready models (shown in dropdown)
- **`beta`**: Testing/development models (shown with [BETA] tag)
- **`deprecated`**: Old models (hidden from dropdown)

## Best Practices

### Configuration
- Use clear, descriptive names and descriptions
- Provide helpful `help_text` for parameters
- Set sensible defaults for optional parameters
- Use appropriate parameter types with validation

### Implementation
- Always validate inference parameters before use
- Return consistent result structures
- Include error handling and clear error messages
- Document expected data formats

### Organization
- One model per directory
- Keep related files together (data, model, utils)
- Use descriptive file names
- Include README in complex models

## Example: Click Model

Location: `src/bayesian_models/click_model/`

**Features:**
- Hierarchical Bayesian model for click-through rates
- County-level random effects
- Multiple inference parameters (county, sample size, confidence level)
- Demographic covariates support

**Files:**
- `config.yaml`: Model metadata and inference parameters
- `click_model.py`: Main model implementation
- `click_model_data.py`: Data loading and preprocessing
- `click_mode_data_preprocessor.py`: Additional preprocessing utilities

## Registry Functions

### In Python Code

```python
from src.causal_models.model_registry import get_registry

# Get registry
registry = get_registry()

# List all models
models = registry.get_all_models()

# Get specific model metadata
metadata = registry.get_model_metadata('click_model')

# Load model instance
model_instance = registry.load_model_instance('click_model')

# Use model
data = model_instance.load_data()
results = model_instance.train(data)
predictions = model_instance.predict({'county': 'Cuyahoga', 'sample_size': 1000})
```

### In Flask Routes

```python
from src.causal_models.model_registry import get_registry


@app.route('/modeling')
def modeling_page():
    registry = get_registry()
    models = registry.get_all_models()
    return render_template('modeling.html', models=models)
```

## Next Steps

### Immediate Priorities
1. Implement training route (`/dashboard/modeling/train`)
2. Implement inference route (`/dashboard/modeling/inference`)
3. Create dynamic form generation from `inference_params`
4. Add result visualization templates

### Future Enhancements
- Model comparison tools
- Training history and logs
- Model versioning and checkpoints
- Export/import trained models
- Automated model diagnostics
- Real-time training progress
