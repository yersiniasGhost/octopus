# Bayesian Model System - Architecture and Usage

**Updated:** 2025-12-05
**Purpose:** Document the Bayesian model metadata system and model management architecture

## Overview

The Bayesian model system provides a standardized way to define, manage, and present statistical models in the UI. Models are auto-discovered from `src/bayesian_models/` and training outputs are stored in `models/{model_id}/`.

## Directory Structure

```
src/bayesian_models/              # Model definitions (auto-discovered)
├── base_model.py                 # Base classes and metadata handling
├── model_registry.py             # Auto-discovery and management
├── {model_id}/                   # Each model in its own directory
│   ├── config.yaml               # Model metadata and inference params
│   ├── {model_id}.py             # Model implementation
│   └── {model_id}_data.py        # Data loading (optional)

src/bayesian_scripts/             # Training scripts (run manually)
├── _template_train.py            # Template for new training scripts
└── {model_id}_train.py           # One script per model

models/                           # Training outputs (gitignored)
└── {model_id}/
    ├── traces/                   # MCMC traces (.nc NetCDF files)
    ├── reports/                  # Summary stats, metrics (.csv, .json)
    ├── diagrams/                 # Visualizations, DAGs (.png, .svg)
    └── checkpoints/              # Model state for inference
```

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
- `ensure_output_dirs()`: Create output directories for training
- `get_output_paths()`: Get dictionary of output directory paths
- `has_trained_model()`: Check if a trained checkpoint exists
- `get_latest_trace()`: Get path to most recent trace file

### 2. Model Registry (`src/bayesian_models/model_registry.py`)

Auto-discovery and management system:

- **`ModelRegistry`**: Scans `src/bayesian_models/` for models with `config.yaml`
- **`get_registry()`**: Global singleton registry instance

**Key Methods:**
- `get_all_models()`: Returns all registered models
- `get_model_metadata(model_id)`: Get specific model metadata
- `load_model_instance(model_id)`: Dynamically load and instantiate model class
- `get_model_for_dropdown()`: Get (id, name) tuples for HTML dropdowns
- `get_model_status(model_id)`: Get model status including training state
- `get_all_models_with_status()`: Get all models with training status

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

training:
  default_iterations: 2000
  chains: 4
  warmup: 1000
  target_accept: 0.95
```

### 4. Training Scripts (`src/bayesian_scripts/`)

Each model has a corresponding training script:

```bash
# Train a model
python src/bayesian_scripts/{model_id}_train.py

# With options
python src/bayesian_scripts/{model_id}_train.py --draws 2000 --chains 4 --gpu
```

Training scripts:
1. Load and prepare data
2. Build the PyMC model
3. Run MCMC sampling (GPU if available)
4. Check convergence diagnostics
5. Save outputs to `models/{model_id}/`

### 5. UI Integration

**Route:** `app/routes/main.py:modeling_dashboard()`
- Loads model registry
- Gets selected model from query params
- Passes model list and details to template

**Template:** `app/templates/dashboards/modeling.html`
- Dropdown for model selection
- Model details display (name, description, version, author, tags)
- Training status indicator
- Action buttons: "Train Model" and "Run Inference"
- Inference parameters table preview

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

training:
  default_iterations: 2000
  chains: 4
  warmup: 1000
  target_accept: 0.95
```

### Step 3: Create Model Implementation

Create `my_new_model/my_new_model.py`:

```python
from pathlib import Path
from typing import Any, Dict
from src.bayesian_models.base_model import BaseBayesianModel


class MyNewModel(BaseBayesianModel):
    """My new Bayesian model implementation"""

    def __init__(self, model_dir: Path):
        super().__init__(model_dir)
        # Additional initialization

    def load_data(self, **kwargs) -> Any:
        """Load and prepare data"""
        # Implementation
        pass

    def train(self, data: Any, **kwargs) -> Dict[str, Any]:
        """Train the model"""
        self.ensure_output_dirs()  # Create output directories
        # Implementation
        return {
            'status': 'success',
            'metrics': {...}
        }

    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """Run inference"""
        is_valid, error = self.validate_inference_params(inference_params)
        if not is_valid:
            return {'error': error}

        # Load trace from self.get_latest_trace()
        # Run inference
        return {
            'predictions': [...],
            'credible_intervals': {...}
        }
```

### Step 4: Create Training Script

```bash
cp src/bayesian_scripts/_template_train.py src/bayesian_scripts/my_new_model_train.py
```

Edit the script:
1. Set `MODEL_ID = 'my_new_model'`
2. Customize `load_training_data()` for your data
3. Customize `build_model()` for your model structure

### Step 5: Train and Verify

```bash
# Train the model
python src/bayesian_scripts/my_new_model_train.py

# Check outputs
ls models/my_new_model/
```

The model will be auto-discovered on next dashboard load.

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

## Model Status Flags

- **`active`**: Production-ready models (shown in dropdown)
- **`beta`**: Testing/development models (shown with [BETA] tag)
- **`deprecated`**: Old models (hidden from dropdown)

## Registry Functions

### In Python Code

```python
from src.bayesian_models.model_registry import get_registry

# Get registry
registry = get_registry()

# List all models
models = registry.get_all_models()

# Get model with training status
status = registry.get_model_status('click_model')
# Returns: {model_id, name, version, status, is_trained, has_trace, last_trained, output_dir}

# Get all models with status
all_status = registry.get_all_models_with_status()

# Load model instance
model = registry.load_model_instance('click_model')

# Access output paths
paths = model.get_output_paths()
# Returns: {output, traces, reports, diagrams, checkpoints}

# Check if trained
if model.has_trained_model():
    trace_path = model.get_latest_trace()
```

### In Flask Routes

```python
from src.bayesian_models.model_registry import get_registry

@app.route('/modeling')
def modeling_page():
    registry = get_registry()
    models = registry.get_all_models_with_status()
    return render_template('modeling.html', models=models)
```

## GPU Acceleration

The system supports GPU acceleration via JAX/NumPyro:

```bash
# Force GPU sampling
python src/bayesian_scripts/click_model_train.py --gpu

# Force CPU sampling
python src/bayesian_scripts/click_model_train.py --cpu
```

Requirements for GPU:
- CUDA toolkit (12.4 recommended)
- JAX with CUDA support: `jax[cuda12_pip]`
- NumPyro: `numpyro`

## Best Practices

### Configuration
- Use clear, descriptive names and descriptions
- Provide helpful `help_text` for parameters
- Set sensible defaults for optional parameters
- Use appropriate parameter types with validation

### Implementation
- Always validate inference parameters before use
- Call `ensure_output_dirs()` before saving training outputs
- Use `get_latest_trace()` to load trained models
- Return consistent result structures
- Include error handling and clear error messages

### Training Scripts
- Copy from `_template_train.py` for consistency
- Include convergence diagnostics
- Save trace, summary, and diagnostic plots
- Use timestamp-based filenames for versioning

### Organization
- One model per directory in `src/bayesian_models/`
- One training script per model in `src/bayesian_scripts/`
- All outputs go to `models/{model_id}/`
- Keep related files together (data, model, utils)
