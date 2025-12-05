"""
Model Registry - Auto-discovery and management of Bayesian models
"""
from pathlib import Path
from typing import Dict, List, Optional
import logging
import importlib.util
import sys

from src.bayesian_models.base_model import (
    BaseBayesianModel, ModelMetadata, MODELS_OUTPUT_DIR
)

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Registry for discovering and managing Bayesian models

    Automatically discovers all models in src/bayesian_models/
    that have a config.yaml file
    """

    def __init__(self, models_dir: Optional[Path] = None):
        if models_dir is None:
            # Default to src/bayesian_models/
            models_dir = Path(__file__).parent

        self.models_dir = Path(models_dir)
        self.models: Dict[str, ModelMetadata] = {}
        self._discover_models()

    def _discover_models(self):
        """Discover all models with config.yaml files"""
        if not self.models_dir.exists():
            logger.warning(f"Models directory does not exist: {self.models_dir}")
            return

        # Look for subdirectories with config.yaml
        for item in self.models_dir.iterdir():
            if item.is_dir() and not item.name.startswith('_') and not item.name.startswith('.'):
                config_path = item / 'config.yaml'
                if config_path.exists():
                    try:
                        metadata = ModelMetadata(config_path)
                        # Only include active and beta models
                        if metadata.status in ['active', 'beta']:
                            self.models[metadata.model_id] = metadata
                            logger.info(f"Registered model: {metadata.name} ({metadata.model_id})")
                    except Exception as e:
                        logger.error(f"Error loading model from {item}: {e}")

    def get_all_models(self) -> List[Dict[str, any]]:
        """
        Get list of all registered models

        Returns:
            List of model metadata dictionaries
        """
        return [metadata.to_dict() for metadata in self.models.values()]

    def get_model_metadata(self, model_id: str) -> Optional[ModelMetadata]:
        """Get metadata for a specific model"""
        return self.models.get(model_id)

    def get_active_models(self) -> List[Dict[str, any]]:
        """Get only active (non-beta) models"""
        return [
            metadata.to_dict()
            for metadata in self.models.values()
            if metadata.status == 'active'
        ]

    def get_models_by_tag(self, tag: str) -> List[Dict[str, any]]:
        """Get models filtered by tag"""
        return [
            metadata.to_dict()
            for metadata in self.models.values()
            if tag in metadata.tags
        ]

    def load_model_instance(self, model_id: str) -> Optional[BaseBayesianModel]:
        """
        Dynamically load and instantiate a model class

        Args:
            model_id: ID of the model to load

        Returns:
            Instance of the model class, or None if not found
        """
        metadata = self.get_model_metadata(model_id)
        if not metadata:
            logger.error(f"Model not found: {model_id}")
            return None

        model_dir = self.models_dir / model_id

        # Try to import the model module
        # Convention: model class is in {model_id}/model.py
        # and class name is derived from model_id (e.g., click_model -> ClickModel)
        try:
            # Try common naming patterns
            possible_modules = [
                f'{model_id}.py',
                'model.py',
                f'{model_id}_model.py'
            ]

            model_module = None
            for module_name in possible_modules:
                module_path = model_dir / module_name
                if module_path.exists():
                    # Dynamic import
                    spec = importlib.util.spec_from_file_location(
                        f"bayesian_models.{model_id}",
                        module_path
                    )
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    model_module = module
                    break

            if not model_module:
                logger.error(f"Could not find model module for {model_id}")
                return None

            # Find the model class (should inherit from BaseBayesianModel)
            for attr_name in dir(model_module):
                attr = getattr(model_module, attr_name)
                if (isinstance(attr, type) and
                        issubclass(attr, BaseBayesianModel) and
                        attr is not BaseBayesianModel):
                    # Found the model class, instantiate it
                    return attr(model_dir)

            logger.error(f"No BaseBayesianModel subclass found in {model_id}")
            return None

        except Exception as e:
            logger.error(f"Error loading model {model_id}: {e}", exc_info=True)
            return None

    def get_model_for_dropdown(self) -> List[tuple[str, str]]:
        """
        Get models formatted for HTML dropdown

        Returns:
            List of (model_id, display_name) tuples
        """
        return [
            (metadata.model_id, f"{metadata.name} (v{metadata.version})")
            for metadata in sorted(
                self.models.values(),
                key=lambda m: m.name
            )
        ]

    def refresh(self):
        """Refresh the model registry (re-discover models)"""
        self.models.clear()
        self._discover_models()

    def get_model_output_dir(self, model_id: str) -> Optional[Path]:
        """Get the output directory for a model"""
        if model_id not in self.models:
            return None
        return MODELS_OUTPUT_DIR / model_id

    def get_model_status(self, model_id: str) -> dict:
        """
        Get comprehensive status of a model including training state.

        Returns:
            dict with keys: model_id, name, version, status, is_trained,
                           has_trace, last_trained, output_dir
        """
        metadata = self.get_model_metadata(model_id)
        if not metadata:
            return None

        output_dir = MODELS_OUTPUT_DIR / model_id
        traces_dir = output_dir / 'traces'
        checkpoints_dir = output_dir / 'checkpoints'

        # Check for trained model artifacts
        has_trace = traces_dir.exists() and any(traces_dir.glob('*.nc'))
        has_checkpoint = checkpoints_dir.exists() and any(checkpoints_dir.iterdir())

        # Get last training time from most recent trace
        last_trained = None
        if has_trace:
            traces = sorted(traces_dir.glob('*.nc'), key=lambda p: p.stat().st_mtime)
            if traces:
                last_trained = traces[-1].stat().st_mtime

        return {
            'model_id': model_id,
            'name': metadata.name,
            'version': metadata.version,
            'status': metadata.status,
            'is_trained': has_trace or has_checkpoint,
            'has_trace': has_trace,
            'last_trained': last_trained,
            'output_dir': str(output_dir)
        }

    def get_all_models_with_status(self) -> List[dict]:
        """Get all models with their training status"""
        return [
            self.get_model_status(model_id)
            for model_id in self.models.keys()
        ]


# Global registry instance
_registry = None


def get_registry() -> ModelRegistry:
    """Get the global model registry instance"""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
