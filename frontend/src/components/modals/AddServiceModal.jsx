import { useState } from 'react';
import { serviceAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import Modal from '../common/Modal';
import Input from '../common/Input';
import Checkbox from '../common/Checkbox';
import Button from '../common/Button';

function AddServiceModal({ projectId, onClose, onSuccess }) {
  const toast = useToast();
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    is_singleton: true,
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name) {
      toast.showWarning('Service name is required');
      return;
    }

    try {
      setLoading(true);
      await serviceAPI.create(projectId, formData);
      toast.showSuccess('Service created successfully');
      onSuccess();
    } catch (error) {
      console.error('Failed to create service:', error);
      toast.showError(error.response?.data?.detail || 'Failed to create service');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Create Service">
      <form onSubmit={handleSubmit}>
        <Input
          label="Service Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="UserService"
          required
        />

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">Description</label>
          <textarea
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Service for managing users..."
            rows="3"
            className="input-field resize-none"
          />
        </div>

        <Checkbox
          label="Singleton"
          description="Single instance for the entire application"
          checked={formData.is_singleton}
          onChange={(e) => setFormData({ ...formData, is_singleton: e.target.checked })}
        />

        <div className="flex justify-end gap-3 pt-4 border-t mt-6">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? 'Creating...' : 'Create Service'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default AddServiceModal;
