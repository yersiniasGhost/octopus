"""
Base class for all Bayesian models with metadata support
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from pathlib import Path
import yaml
import logging

logger = logging.getLogger(__name__)


class InferenceParameter:
    """Represents a single inference parameter with metadata"""

    def __init__(self, name: str, param_type: str, label: str,
                 default: Any = None, required: bool = True,
                 min_value: Optional[float] = None,
                 max_value: Optional[float] = None,
                 options: Optional[List[str]] = None,
                 help_text: Optional[str] = None):
        self.name = name
        self.param_type = param_type  # 'integer', 'float', 'string', 'select', 'boolean'
        self.label = label
        self.default = default
        self.required = required
        self.min_value = min_value
        self.max_value = max_value
        self.options = options  # For select type
        self.help_text = help_text

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'name': self.name,
            'type': self.param_type,
            'label': self.label,
            'default': self.default,
            'required': self.required,
            'min_value': self.min_value,
            'max_value': self.max_value,
            'options': self.options,
            'help_text': self.help_text
        }


class ModelMetadata:
    """Model metadata loaded from config.yaml"""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.model_id = config_path.parent.name
        self.config = self._load_config()

        self.name = self.config.get('name', self.model_id)
        self.description = self.config.get('description', '')
        self.version = self.config.get('version', '1.0')
        self.author = self.config.get('author', 'Unknown')
        self.tags = self.config.get('tags', [])
        self.status = self.config.get('status', 'active')  # active, beta, deprecated

        # Parse inference parameters
        self.inference_params = self._parse_inference_params()

    def _load_config(self) -> Dict[str, Any]:
        """Load YAML configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading config from {self.config_path}: {e}")
            return {}

    def _parse_inference_params(self) -> List[InferenceParameter]:
        """Parse inference parameters from config"""
        params = []
        param_configs = self.config.get('inference_params', [])

        for param_config in param_configs:
            param = InferenceParameter(
                name=param_config['name'],
                param_type=param_config.get('type', 'string'),
                label=param_config.get('label', param_config['name']),
                default=param_config.get('default'),
                required=param_config.get('required', True),
                min_value=param_config.get('min_value'),
                max_value=param_config.get('max_value'),
                options=param_config.get('options'),
                help_text=param_config.get('help_text')
            )
            params.append(param)

        return params

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'model_id': self.model_id,
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'author': self.author,
            'tags': self.tags,
            'status': self.status,
            'inference_params': [p.to_dict() for p in self.inference_params]
        }


class BaseBayesianModel(ABC):
    """
    Abstract base class for all Bayesian models

    Each model should:
    1. Have a config.yaml in its directory
    2. Implement train(), predict(), and load_data() methods
    3. Store results in a consistent format
    """

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self.model_id = self.model_dir.name

        # Load metadata from config.yaml
        config_path = self.model_dir / 'config.yaml'
        if not config_path.exists():
            raise FileNotFoundError(
                f"config.yaml not found in {self.model_dir}. "
                f"Each model must have a config.yaml file."
            )

        self.metadata = ModelMetadata(config_path)
        logger.info(f"Loaded model: {self.metadata.name} (v{self.metadata.version})")

    @abstractmethod
    def load_data(self, **kwargs) -> Any:
        """
        Load and prepare data for model training

        Returns:
            Prepared data ready for model training
        """
        pass

    @abstractmethod
    def train(self, data: Any, **kwargs) -> Dict[str, Any]:
        """
        Train the Bayesian model

        Args:
            data: Prepared data from load_data()
            **kwargs: Additional training parameters

        Returns:
            Dictionary with training results and metrics
        """
        pass

    @abstractmethod
    def predict(self, inference_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run inference with the trained model

        Args:
            inference_params: Dictionary of inference parameters

        Returns:
            Dictionary with prediction results and diagnostics
        """
        pass

    def get_inference_form_fields(self) -> List[Dict[str, Any]]:
        """
        Get form field definitions for inference UI

        Returns:
            List of field definitions for HTML form rendering
        """
        return [param.to_dict() for param in self.metadata.inference_params]

    def validate_inference_params(self, params: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate inference parameters

        Returns:
            (is_valid, error_message)
        """
        for param_def in self.metadata.inference_params:
            # Check required parameters
            if param_def.required and param_def.name not in params:
                return False, f"Missing required parameter: {param_def.label}"

            if param_def.name in params:
                value = params[param_def.name]

                # Type-specific validation
                if param_def.param_type == 'integer':
                    try:
                        int_val = int(value)
                        if param_def.min_value is not None and int_val < param_def.min_value:
                            return False, f"{param_def.label} must be >= {param_def.min_value}"
                        if param_def.max_value is not None and int_val > param_def.max_value:
                            return False, f"{param_def.label} must be <= {param_def.max_value}"
                    except ValueError:
                        return False, f"{param_def.label} must be an integer"

                elif param_def.param_type == 'float':
                    try:
                        float_val = float(value)
                        if param_def.min_value is not None and float_val < param_def.min_value:
                            return False, f"{param_def.label} must be >= {param_def.min_value}"
                        if param_def.max_value is not None and float_val > param_def.max_value:
                            return False, f"{param_def.label} must be <= {param_def.max_value}"
                    except ValueError:
                        return False, f"{param_def.label} must be a number"

                elif param_def.param_type == 'select':
                    if param_def.options and value not in param_def.options:
                        return False, f"{param_def.label} must be one of: {', '.join(param_def.options)}"

        return True, None

    def get_metadata_dict(self) -> Dict[str, Any]:
        """Get model metadata as dictionary"""
        return self.metadata.to_dict()
