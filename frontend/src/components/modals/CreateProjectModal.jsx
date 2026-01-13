import { useState } from 'react';
import { projectAPI } from '../../services/api';
import { FRAMEWORKS } from '../../utils/constants';
import { useToast } from '../common/ToastContainer';
import Modal from '../common/Modal';
import Input from '../common/Input';
import Button from '../common/Button';

function CreateProjectModal({ onClose, onProjectCreated }) {
  const toast = useToast();
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    version: '1.0.0',
    framework: 'fastapi',
  });
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(false);

  const validateForm = () => {
    const newErrors = {};

    if (!formData.name.trim()) {
      newErrors.name = 'Project name is required';
    } else if (formData.name.length > 100) {
      newErrors.name = 'Project name must be less than 100 characters';
    }

    if (!formData.version.trim()) {
      newErrors.version = 'Version is required';
    }

    if (!formData.framework) {
      newErrors.framework = 'Framework is required';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) return;

    try {
      setLoading(true);
      const response = await projectAPI.create(formData);
      toast.showSuccess(`Project "${formData.name}" created successfully!`);
      onProjectCreated(response.data);
    } catch (error) {
      console.error('Failed to create project:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to create project. Please try again.';
      toast.showError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field, value) => {
    setFormData({ ...formData, [field]: value });
    // Clear error for this field
    if (errors[field]) {
      setErrors({ ...errors, [field]: '' });
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Create New Project" size="max-w-3xl">
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Input
            label="Project Name"
            value={formData.name}
            onChange={(e) => handleChange('name', e.target.value)}
            placeholder="My Awesome API"
            required
            error={errors.name}
          />

          <Input
            label="Version"
            value={formData.version}
            onChange={(e) => handleChange('version', e.target.value)}
            placeholder="1.0.0"
            required
            error={errors.version}
          />
        </div>

        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Description
          </label>
          <textarea
            value={formData.description}
            onChange={(e) => handleChange('description', e.target.value)}
            placeholder="A brief description of this project..."
            rows="3"
            className="input-field resize-none"
          />
        </div>

        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-3">
            Framework
          </label>
          <div className="rounded-lg border-2 border-accent-gold bg-primary-50 p-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2">
                <img src="/assets/python.svg" alt="Python" className="w-12 h-12" />
                <span className="text-accent-gold text-2xl font-bold">+</span>
                <img src="/assets/fastapi.svg" alt="FastAPI" className="w-12 h-12" />
              </div>
              <div>
                <h4 className="font-semibold text-gray-800">Python + FastAPI</h4>
                <p className="text-sm text-gray-500">Modern Python web framework for building APIs</p>
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? 'Creating...' : 'Create Project'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default CreateProjectModal;
