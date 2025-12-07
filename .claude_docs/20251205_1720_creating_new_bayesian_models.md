# Creating New Bayesian Models

This guide documents the process of creating new model versions by copying and modifying existing models. This is the standard workflow for iterative model development.

## Directory Structure

```
src/
├── bayesian_models/
│   ├── click_model/           # Base model (v01)
│   │   ├── __init__.py        # Package exports
│   │   ├── model.py           # Core model class (ClickModel, SegmentPredictor)
│   │   ├── model_data.py      # Data loading and ClickModelData class
│   │   ├── model_data_preprocessor.py  # Standardization
│   │   ├── segments.py        # Segment definitions
│   │   └── config.yaml        # Model configuration
│   │
│   └── click_model_02/        # Extended model (v02)
│       └── (same structure)
│
└── bayesian_scripts/
    ├── train_model.py         # Training script for click_model
    └── train_click_model_02.py  # Training script for click_model_02
```

## Step-by-Step Process

### Step 1: Copy the Base Model Folder

```bash
cp -r src/bayesian_models/click_model src/bayesian_models/click_model_02
```

This creates an exact copy of all files. Do NOT use inheritance - each model version is self-contained.

### Step 2: Modify model_data.py

Update the data loading to include new variables:

1. **Add new data source functions** (if needed):
   ```python
   def load_new_data_source(db, verbose: bool = True) -> Dict[str, dict]:
       """Load new data indexed by join key."""
       # Implementation
   ```

2. **Update ClickModelData class**:
   ```python
   @dataclass
   class ClickModelData:
       # Existing fields...
       new_variable: np.ndarray  # NEW: Description
   ```

3. **Update load_data() function**:
   - Add new data source loading
   - Update the join logic
   - Add new field to ClickModelData construction

4. **Update summary() method** to display new variable stats

5. **Update _load_synthetic_data()** for testing

### Step 3: Modify model_data_preprocessor.py

1. **Add standardization parameters**:
   ```python
   def __init__(self):
       # Existing...
       self.new_var_mean: float = None
       self.new_var_std: float = None
   ```

2. **Update fit() method**:
   ```python
   self.new_var_mean = data.new_variable.mean()
   self.new_var_std = data.new_variable.std()
   ```

3. **Update transform() method**:
   ```python
   result['new_var_std'] = (data.new_variable - self.new_var_mean) / self.new_var_std
   ```

4. **Update transform_new()** for predictions:
   ```python
   def transform_new(self, ..., new_variable: float, ...) -> Dict[str, float]:
   ```

### Step 4: Modify model.py

1. **Update build_model()** - add new predictor:
   ```python
   with pm.Model() as model:
       # Data
       new_var_std = pm.Data('new_var_std', model_data['new_var_std'])

       # Priors - add new coefficient
       beta_new_var = pm.Normal('beta_new_var', mu=0, sigma=0.5)

       # Linear combination - add term
       logit_p = (alpha
                  + beta_income * income_std
                  + beta_eb * eb_std
                  + beta_new_var * new_var_std)  # NEW
   ```

2. **Update fit()** - check new parameter in convergence

3. **Update summary()** - include new coefficient

4. **Update plot methods** if needed

5. **Update SegmentPredictor.predict_segment()**:
   ```python
   def predict_segment(self, income: float, energy_burden: float,
                       new_variable: float, ...) -> Dict[str, float]:
   ```

6. **Update compare_segments()** to extract new variable from segments

### Step 5: Modify segments.py

1. **Add new variable to ALL existing segments**:
   ```python
   DEFAULT_SEGMENTS = [
       {
           'name': 'Segment Name',
           'income': 25000,
           'energy_burden': 20,
           'new_variable': 35,  # ADD to every segment
       },
       # ...
   ]
   ```

2. **Create new focused segments** (optional):
   ```python
   NEW_VARIABLE_FOCUSED_SEGMENTS = [
       {'name': 'Low New Var', 'income': 50000, 'energy_burden': 10, 'new_variable': 10},
       {'name': 'High New Var', 'income': 50000, 'energy_burden': 10, 'new_variable': 80},
   ]
   ```

3. **Update create_segment() utility** to include new variable

### Step 6: Update __init__.py

1. **Update module docstring** with version description
2. **Add new segment exports**:
   ```python
   from .segments import (
       DEFAULT_SEGMENTS,
       NEW_VARIABLE_FOCUSED_SEGMENTS,  # NEW
   )
   ```
3. **Update __all__ list**

### Step 7: Create Training Script

Copy and modify the training script:

```bash
cp src/bayesian_scripts/train_model.py src/bayesian_scripts/train_click_model_02.py
```

Update:
1. Import paths to use new model package
2. Script docstring and print statements
3. Add new coefficient interpretation
4. Add new segment comparison outputs
5. Update metadata with new predictor list

## Example: Adding House Age (click_model → click_model_02)

| File | Key Changes |
|------|-------------|
| `model_data.py` | Added `load_residential_index()`, joined via `parcel_id`, added `house_age` field |
| `model_data_preprocessor.py` | Added `house_age_mean`, `house_age_std`, updated all transform methods |
| `model.py` | Added `beta_house_age` prior and term in linear combination |
| `segments.py` | Added `house_age` to all segments, created `HOUSE_AGE_FOCUSED_SEGMENTS` |
| `__init__.py` | Updated docstring and exports |
| `train_click_model_02.py` | Added house age coefficient interpretation and segment analysis |

## Database Joins Reference

Current join chain for click_model_02:
```
Participant (email) → Demographic (email) → Residential (parcel_id)
                      ↓                      ↓
                      income, energy_burden  house_age (year_built)
```

## Naming Conventions

- **Model folders**: `click_model`, `click_model_02`, `click_model_03`, etc.
- **Training scripts**: `train_model.py` (base), `train_click_model_02.py`, etc.
- **Output directories**: `models/click_model_02/YYYYMMDD_HHMMSS/`

## Testing New Models

Quick validation test:
```python
from src.bayesian_models.click_model_02 import load_data, ClickModel

data = load_data()
model = ClickModel()
model.build_model(data)
trace = model.fit(draws=100, tune=50, chains=2)  # Quick test
print(model.summary())
```

Full training:
```bash
python src/bayesian_scripts/train_click_model_02.py --draws 2000 --chains 4
```

## Checklist for New Model Versions

- [ ] Copy folder: `cp -r click_model_XX click_model_YY`
- [ ] Update `model_data.py` with new data sources and fields
- [ ] Update `model_data_preprocessor.py` with new standardization
- [ ] Update `model.py` with new priors and linear terms
- [ ] Update `segments.py` - add new field to ALL segments
- [ ] Update `__init__.py` docstring and exports
- [ ] Create training script in `bayesian_scripts/`
- [ ] Test imports: `from src.bayesian_models.click_model_YY import ...`
- [ ] Run quick training test
- [ ] Run full training and validate convergence
