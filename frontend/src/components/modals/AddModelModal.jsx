import { useState, useEffect } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { modelAPI } from '../../services/api';
import { DB_FIELD_TYPES } from '../../utils/constants';
import { generateTableName, generateId } from '../../utils/helpers';
import { useToast } from '../common/ToastContainer';
import Modal from '../common/Modal';
import Input from '../common/Input';
import Select from '../common/Select';
import Checkbox from '../common/Checkbox';
import Button from '../common/Button';

function AddModelModal({ projectId, model, onClose, onSuccess }) {
  const toast = useToast();
  const [formData, setFormData] = useState({
    name: '',
    table_name: '',
    fields: [],
  });
  const [loading, setLoading] = useState(false);
  const [tableNameManuallyEdited, setTableNameManuallyEdited] = useState(false);

  useEffect(() => {
    if (model) {
      setFormData({
        name: model.name,
        table_name: model.table_name,
        fields: model.fields || [],
      });
      setTableNameManuallyEdited(true); // Don't auto-update if editing existing model
    } else {
      // Add default id field for new models
      setFormData({
        name: '',
        table_name: '',
        fields: [
          {
            id: generateId(),
            name: 'id',
            type: 'integer',
            nullable: false,
            unique: true,
            default: null,
            primary_key: true,
            index: false,
            max_length: null,
          },
        ],
      });
    }
  }, [model]);

  const handleNameChange = (name) => {
    setFormData({
      ...formData,
      name,
      // Auto-generate table name if user hasn't manually edited it
      table_name: tableNameManuallyEdited ? formData.table_name : generateTableName(name),
    });
  };

  const handleTableNameChange = (tableName) => {
    setFormData({
      ...formData,
      table_name: tableName,
    });
    setTableNameManuallyEdited(true); // Mark as manually edited
  };

  const handleAddField = () => {
    setFormData({
      ...formData,
      fields: [
        ...formData.fields,
        {
          id: generateId(),
          name: '',
          type: 'string',
          nullable: true,
          unique: false,
          default: null,
          primary_key: false,
          index: false,
          max_length: null,
        },
      ],
    });
  };

  const handleRemoveField = (fieldId) => {
    setFormData({
      ...formData,
      fields: formData.fields.filter((f) => f.id !== fieldId),
    });
  };

  const handleFieldChange = (fieldId, key, value) => {
    setFormData({
      ...formData,
      fields: formData.fields.map((f) =>
        f.id === fieldId ? { ...f, [key]: value } : f
      ),
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name || formData.fields.length === 0) {
      toast.showWarning('Model name and at least one field are required');
      return;
    }

    try {
      setLoading(true);
      // Remove temporary IDs before sending
      const dataToSend = {
        ...formData,
        fields: formData.fields.map(({ id, ...field }) => field),
      };

      if (model) {
        await modelAPI.update(projectId, model.id, dataToSend);
        toast.showSuccess(`Model "${formData.name}" updated successfully!`);
      } else {
        await modelAPI.create(projectId, dataToSend);
        toast.showSuccess(`Model "${formData.name}" created successfully!`);
      }
      onSuccess();
    } catch (error) {
      console.error('Failed to save model:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to save model';
      toast.showError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={model ? 'Edit Data Model' : 'Create Data Model'}
      size="max-w-4xl"
    >
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <Input
            label="Model Name"
            value={formData.name}
            onChange={(e) => handleNameChange(e.target.value)}
            placeholder="User"
            required
          />
          <Input
            label="Table Name"
            value={formData.table_name}
            onChange={(e) => handleTableNameChange(e.target.value)}
            placeholder="users"
            required
          />
        </div>

        <div className="mb-4">
          <div className="flex justify-between items-center mb-3">
            <label className="text-sm font-medium text-gray-700">Fields</label>
            <Button type="button" variant="outline" onClick={handleAddField} className="text-sm">
              <Plus className="w-4 h-4 mr-1" />
              Add Field
            </Button>
          </div>

          <div className="space-y-3 max-h-96 overflow-y-auto">
            {formData.fields.map((field, index) => (
              <div key={field.id} className="border rounded-lg p-4 bg-gray-50">
                <div className="grid grid-cols-3 gap-3 mb-3">
                  <Input
                    label="Field Name"
                    value={field.name}
                    onChange={(e) => handleFieldChange(field.id, 'name', e.target.value)}
                    placeholder="email"
                    required
                  />
                  <Select
                    label="Type"
                    value={field.type}
                    onChange={(e) => handleFieldChange(field.id, 'type', e.target.value)}
                    options={DB_FIELD_TYPES}
                    required
                  />
                  {field.type === 'string' && (
                    <Input
                      label="Max Length"
                      type="number"
                      value={field.max_length || ''}
                      onChange={(e) =>
                        handleFieldChange(field.id, 'max_length', e.target.value ? parseInt(e.target.value) : null)
                      }
                      placeholder="255"
                    />
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3 mb-3">
                  <Checkbox
                    label="Primary Key"
                    checked={field.primary_key}
                    onChange={(e) => handleFieldChange(field.id, 'primary_key', e.target.checked)}
                  />
                  <Checkbox
                    label="Unique"
                    checked={field.unique}
                    onChange={(e) => handleFieldChange(field.id, 'unique', e.target.checked)}
                  />
                  <Checkbox
                    label="Nullable"
                    checked={field.nullable}
                    onChange={(e) => handleFieldChange(field.id, 'nullable', e.target.checked)}
                  />
                  <Checkbox
                    label="Index"
                    checked={field.index}
                    onChange={(e) => handleFieldChange(field.id, 'index', e.target.checked)}
                  />
                </div>

                <div className="flex justify-end">
                  <button
                    type="button"
                    onClick={() => handleRemoveField(field.id)}
                    className="text-red-600 hover:text-red-700 text-sm flex items-center gap-1"
                  >
                    <Trash2 className="w-4 h-4" />
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading ? 'Saving...' : model ? 'Update Model' : 'Create Model'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default AddModelModal;
