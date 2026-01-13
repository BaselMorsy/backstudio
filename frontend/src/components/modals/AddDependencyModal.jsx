import { useState } from 'react';
import { dependencyAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import { DEPENDENCY_TYPES, DEPENDENCY_SCOPES } from '../../utils/constants';
import Modal from '../common/Modal';
import Input from '../common/Input';
import Select from '../common/Select';
import Checkbox from '../common/Checkbox';
import Button from '../common/Button';

function AddDependencyModal({ projectId, onClose, onSuccess }) {
  const toast = useToast();
  const [formData, setFormData] = useState({
    name: '',
    type: 'provider',
    description: '',
    scope: 'request',
    function_name: '',
    return_type: '',
    is_async: true,
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name || !formData.function_name) {
      toast.showWarning('Name and function name are required');
      return;
    }

    try {
      setLoading(true);
      await dependencyAPI.create(projectId, {
        ...formData,
        parameters: [], // Can be extended later
      });
      toast.showSuccess('Dependency created successfully');
      onSuccess();
    } catch (error) {
      console.error('Failed to create dependency:', error);
      toast.showError(error.response?.data?.detail || 'Failed to create dependency');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Create Dependency Injection">
      <form onSubmit={handleSubmit}>
        <Input
          label="Dependency Name"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="CurrentUserProvider"
          required
        />

        <div className="grid grid-cols-2 gap-4">
          <Select
            label="Type"
            value={formData.type}
            onChange={(e) => setFormData({ ...formData, type: e.target.value })}
            options={DEPENDENCY_TYPES}
            required
          />

          <Select
            label="Scope"
            value={formData.scope}
            onChange={(e) => setFormData({ ...formData, scope: e.target.value })}
            options={DEPENDENCY_SCOPES}
            required
          />
        </div>

        <Input
          label="Function Name"
          value={formData.function_name}
          onChange={(e) => setFormData({ ...formData, function_name: e.target.value })}
          placeholder="get_current_user"
          required
        />

        <Input
          label="Return Type"
          value={formData.return_type}
          onChange={(e) => setFormData({ ...formData, return_type: e.target.value })}
          placeholder="User"
        />

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">Description</label>
          <textarea
            value={formData.description}
            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
            placeholder="Provides the current authenticated user..."
            rows="3"
            className="input-field resize-none"
          />
        </div>

        <Checkbox
          label="Async Function"
          description="Function uses async/await"
          checked={formData.is_async}
          onChange={(e) => setFormData({ ...formData, is_async: e.target.checked })}
        />

        <div className="flex justify-end gap-3 pt-4 border-t mt-6">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? 'Creating...' : 'Create Dependency'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default AddDependencyModal;
