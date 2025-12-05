from typing import Optional
from dataclasses import dataclass
import numpy as np
import pandas as pd


# =============================================================================
# DATA FORMAT SPECIFICATION
# =============================================================================

@dataclass
class ClickModelData:
    """
    Data container for the click-through model.

    This dataclass defines the exact format expected by the model.
    Populate this structure with your actual data.

    Attributes
    ----------
    contact_id : np.ndarray
        Unique identifier for each contact (for tracking, not used in model)
        Shape: (n_contacts,)

    age : np.ndarray
        Age of contact in years (will be standardized internally)
        Shape: (n_contacts,)
        Example: [25, 34, 67, 45, ...]

    income : np.ndarray
        Annual household income in dollars (will be standardized internally)
        Shape: (n_contacts,)
        Example: [35000, 75000, 120000, ...]

    energy_burden : np.ndarray
        Energy burden as percentage of income spent on energy (0-100 scale)
        (will be standardized internally)
        Shape: (n_contacts,)
        Example: [3.5, 8.2, 15.0, ...]  # 3.5% of income on energy

    click : np.ndarray
        Binary outcome: 1 = clicked, 0 = did not click
        Shape: (n_contacts,)
        Example: [0, 0, 1, 0, 0, 0, 1, ...]

    # ----- TREATMENT VARIABLES (for Version 1+) -----
    # Include these in your data even for Version 0 so structure is ready

    channel : Optional[np.ndarray]
        Communication channel used. Categories:
        - 'email': Email campaign
        - 'text': Text message
        - 'mailer': Physical mailer/letter
        Shape: (n_contacts,)
        Example: ['email', 'text', 'email', 'mailer', ...]

    timing : Optional[np.ndarray]
        Time of day message was sent. Categories:
        - 'morning': Before 12pm
        - 'afternoon': 12pm - 5pm
        - 'evening': After 5pm
        Shape: (n_contacts,)
        Example: ['morning', 'evening', 'afternoon', ...]

    campaign_name : Optional[np.ndarray]
        Name/ID of specific campaign (especially for the 69 email campaigns)
        Shape: (n_contacts,)
        Example: ['summer_savings_2024', 'urgent_deadline', ...]

    framing : Optional[np.ndarray]
        Message framing type. Categories:
        - 'hopeful': Positive, aspirational messaging
        - 'funny': Humorous approach
        - 'urgent': Time-sensitive, action-oriented
        Shape: (n_contacts,)
        Example: ['hopeful', 'urgent', 'funny', ...]
    """
    # Required for Version 0
    contact_id: np.ndarray
    age: np.ndarray
    income: np.ndarray
    energy_burden: np.ndarray
    click: np.ndarray

    # Optional for Version 0, required for Version 1+
    channel: Optional[np.ndarray] = None
    timing: Optional[np.ndarray] = None
    campaign_name: Optional[np.ndarray] = None
    framing: Optional[np.ndarray] = None



    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()



    def _validate(self):
        """Run validation checks on the data."""
        n = len(self.contact_id)

        # Check all required arrays have same length
        assert len(self.age) == n, f"age length {len(self.age)} != {n}"
        assert len(self.income) == n, f"income length {len(self.income)} != {n}"
        assert len(self.energy_burden) == n, f"energy_burden length {len(self.energy_burden)} != {n}"
        assert len(self.click) == n, f"click length {len(self.click)} != {n}"

        # Check click is binary
        assert set(np.unique(self.click)).issubset({0, 1}), "click must be binary (0 or 1)"

        # Check for missing values
        assert not np.any(np.isnan(self.age)), "age contains NaN values"
        assert not np.any(np.isnan(self.income)), "income contains NaN values"
        assert not np.any(np.isnan(self.energy_burden)), "energy_burden contains NaN values"

        print(f"✓ Data validated: {n} contacts, {self.click.sum()} clicks ({100 * self.click.mean():.2f}% CTR)")



    @property
    def n_contacts(self) -> int:
        """Number of contacts in dataset."""
        return len(self.contact_id)



    @property
    def click_rate(self) -> float:
        """Overall click-through rate."""
        return self.click.mean()



    def summary(self) -> pd.DataFrame:
        """Return summary statistics for the data."""
        return pd.DataFrame({
            'Variable': ['Age', 'Income', 'Energy Burden', 'Click'],
            'Mean': [self.age.mean(), self.income.mean(), self.energy_burden.mean(), self.click.mean()],
            'Std': [self.age.std(), self.income.std(), self.energy_burden.std(), self.click.std()],
            'Min': [self.age.min(), self.income.min(), self.energy_burden.min(), self.click.min()],
            'Max': [self.age.max(), self.income.max(), self.energy_burden.max(), self.click.max()]
        })


def load_data() -> ClickModelData:
    """
    ============================================================================
    USER: POPULATE THIS FUNCTION WITH YOUR ACTUAL DATA
    ============================================================================

    This function should return a ClickModelData object populated with your data.

    Example implementation with synthetic data (replace with your data loading):

    Returns
    -------
    ClickModelData
        Populated data container ready for modeling

    Example
    -------
    >>> # Load from CSV
    >>> df = pd.read_csv('your_data.csv')
    >>> data = ClickModelData(
    ...     contact_id=df['contact_id'].values,
    ...     age=df['age'].values,
    ...     income=df['income'].values,
    ...     energy_burden=df['energy_burden'].values,
    ...     click=df['clicked'].values,
    ...     channel=df['channel'].values,  # Optional for V0
    ...     timing=df['send_time'].values,  # Optional for V0
    ...     framing=df['message_type'].values  # Optional for V0
    ... )
    >>> return data
    """
    # -------------------------------------------------------------------------
    # REPLACE THIS SECTION WITH YOUR DATA LOADING CODE
    # -------------------------------------------------------------------------

    # Example: Generate synthetic data for testing
    # DELETE THIS AND REPLACE WITH YOUR ACTUAL DATA
    np.random.seed(42)
    n = 10000  # Number of contacts

    # Simulate demographics
    age = np.random.normal(45, 15, n).clip(18, 85)
    income = np.random.lognormal(10.8, 0.5, n).clip(15000, 500000)  # Median ~50k
    energy_burden = np.random.exponential(6, n).clip(1, 30)  # Right-skewed, mean ~6%

    # Simulate click probability (true data generating process)
    # Higher energy burden → higher click (they need help)
    # Middle income → higher click (can act but needs savings)
    # Younger → slightly higher click (more digital engagement)
    logit_p = (
            -4.0  # Baseline (gives ~2-3% CTR)
            + 0.3 * ((energy_burden - 6) / 5)  # Energy burden effect
            - 0.1 * ((age - 45) / 15)  # Age effect (younger = higher)
            + 0.2 * np.exp(-((income - 60000) / 30000) ** 2)  # Middle income peak
    )
    p_click = 1 / (1 + np.exp(-logit_p))
    click = np.random.binomial(1, p_click)

    # Simulate treatment variables (for later versions)
    channels = np.random.choice(['email', 'text', 'mailer'], n, p=[0.6, 0.25, 0.15])
    timings = np.random.choice(['morning', 'afternoon', 'evening'], n)
    framings = np.random.choice(['hopeful', 'funny', 'urgent'], n)

    print("⚠️  Using SYNTHETIC data - replace load_data() with your actual data!")

    return ClickModelData(
        contact_id=np.arange(n),
        age=age,
        income=income,
        energy_burden=energy_burden,
        click=click,
        channel=channels,
        timing=timings,
        framing=framings
    )

    # -------------------------------------------------------------------------
    # END OF SECTION TO REPLACE
    # -------------------------------------------------------------------------

