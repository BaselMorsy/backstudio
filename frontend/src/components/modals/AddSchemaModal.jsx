import { useState, useEffect } from 'react';
import { X, Save, Plus, Trash2 } from 'lucide-react';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import { schemaAPI } from '../../services/api';
import { PYTHON_TYPES } from '../../utils/constants';

function AddSchemaModal({ projectId, serviceId, initialData, onClose, onSuccess }) {
  const toast = useToast();
  const isEditMode = !!initialData;

  // Parse existing field types to extract modifiers
  const parseFieldType = (typeString) => {
    let baseType = typeString;
    let is_optional = false;
    let is_list = false;

    // Check for Optional wrapper
    if (typeString.startsWith('Optional[') && typeString.endsWith(']')) {
      is_optional = true;
      baseType = typeString.slice(9, -1); // Remove "Optional[" and "]"
    }

    // Check for List wrapper
    if (baseType.startsWith('List[') && baseType.endsWith(']')) {
      is_list = true;
      baseType = baseType.slice(5, -1); // Remove "List[" and "]"
    }

    // Determine type category (primitive vs synthetic)
    const type_category = PYTHON_TYPES.includes(baseType) ? 'primitive' : 'synthetic';

    return { type: baseType, is_list, is_optional, type_category };
  };

  // Process initial data fields
  const processInitialFields = (fields) => {
    return fields.map(field => ({
      ...field,
      ...parseFieldType(field.type),
    }));
  };

  const [formData, setFormData] = useState(
    initialData
      ? {
          ...initialData,
          fields: processInitialFields(initialData.fields || []),
        }
      : {
          name: '',
          description: '',
          fields: [],
        }
  );
  const [saving, setSaving] = useState(false);
  const [availableSchemas, setAvailableSchemas] = useState([]);

  // Fetch available schemas for type selection
  useEffect(() => {
    const fetchSchemas = async () => {
      try {
        const response = await schemaAPI.getAll(projectId, serviceId);
        setAvailableSchemas(response.data || []);
      } catch (error) {
        console.error('Failed to fetch schemas:', error);
      }
    };
    fetchSchemas();
  }, [projectId, serviceId]);

  const handleAddField = () => {
    setFormData({
      ...formData,
      fields: [
        ...formData.fields,
        {
          name: '',
          type: 'str',
          type_category: 'primitive',
          required: false,
          description: '',
          is_list: false,
          is_optional: false,
        },
      ],
    });
  };

  const handleUpdateField = (index, field) => {
    const newFields = [...formData.fields];
    newFields[index] = field;
    setFormData({ ...formData, fields: newFields });
  };

  const handleRemoveField = (index) => {
    const newFields = formData.fields.filter((_, i) => i !== index);
    setFormData({ ...formData, fields: newFields });
  };

  const buildFieldType = (field) => {
    let baseType = field.type || 'string';

    // Build the type string based on modifiers
    if (field.is_list) {
      baseType = `List[${baseType}]`;
    }

    if (field.is_optional) {
      baseType = `Optional[${baseType}]`;
    }

    return baseType;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name.trim()) {
      toast.showWarning('Schema name is required');
      return;
    }

    // Build final type strings for all fields
    const processedFields = formData.fields.map(field => ({
      name: field.name,
      type: buildFieldType(field),
      required: field.required,
      description: field.description,
    }));

    const payload = {
      ...formData,
      fields: processedFields,
    };

    try {
      setSaving(true);
      if (isEditMode) {
        await schemaAPI.update(projectId, serviceId, initialData.id, payload);
        toast.showSuccess('Schema updated successfully');
      } else {
        await schemaAPI.create(projectId, serviceId, payload);
        toast.showSuccess('Schema created successfully');
      }
      onSuccess();
    } catch (error) {
      console.error(`Failed to ${isEditMode ? 'update' : 'create'} schema:`, error);
      toast.showError(error.response?.data?.detail || `Failed to ${isEditMode ? 'update' : 'create'} schema`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="px-6 py-4 border-b flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-800">
            {isEditMode ? 'Edit Schema (DTO)' : 'Add Schema (DTO)'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Schema Name *
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              placeholder="e.g., UserCreateDTO"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Description
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
              rows="2"
              placeholder="Schema description..."
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm font-medium text-gray-700">
                Fields
              </label>
              <Button type="button" size="sm" onClick={handleAddField}>
                <Plus className="w-4 h-4 mr-1" />
                Add Field
              </Button>
            </div>

            <div className="space-y-3">
              {formData.fields.map((field, index) => (
                <div key={index} className="border border-gray-200 rounded-lg p-4">
                  {/* Field name and delete button */}
                  <div className="flex gap-3 mb-3">
                    <input
                      type="text"
                      value={field.name}
                      onChange={(e) =>
                        handleUpdateField(index, { ...field, name: e.target.value })
                      }
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
                      placeholder="Field name"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveField(index)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="Remove field"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Type category radio buttons */}
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-2">
                      Type Category
                    </label>
                    <div className="flex gap-4">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name={`type-category-${index}`}
                          value="primitive"
                          checked={(field.type_category || 'primitive') === 'primitive'}
                          onChange={(e) =>
                            handleUpdateField(index, {
                              ...field,
                              type_category: 'primitive',
                              type: 'str',
                            })
                          }
                          className="text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">Primitive Type</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="radio"
                          name={`type-category-${index}`}
                          value="synthetic"
                          checked={(field.type_category || 'primitive') === 'synthetic'}
                          onChange={(e) =>
                            handleUpdateField(index, {
                              ...field,
                              type_category: 'synthetic',
                              type: availableSchemas[0]?.name || '',
                            })
                          }
                          className="text-primary-600 focus:ring-primary-500"
                        />
                        <span className="text-sm text-gray-700">Synthetic Type</span>
                      </label>
                    </div>
                  </div>

                  {/* Base type selector */}
                  <div className="mb-3">
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      Base Type
                    </label>
                    <select
                      value={field.type}
                      onChange={(e) =>
                        handleUpdateField(index, { ...field, type: e.target.value })
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                    >
                      {(field.type_category || 'primitive') === 'primitive'
                        ? PYTHON_TYPES.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))
                        : availableSchemas.map((schema) => (
                            <option key={schema.id} value={schema.name}>
                              {schema.name}
                            </option>
                          ))}
                      {(field.type_category || 'primitive') === 'synthetic' &&
                        availableSchemas.length === 0 && (
                          <option value="">No schemas available</option>
                        )}
                    </select>
                  </div>

                  {/* Type modifiers */}
                  <div className="flex flex-wrap gap-4 mb-3">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={field.is_list || false}
                        onChange={(e) =>
                          handleUpdateField(index, { ...field, is_list: e.target.checked })
                        }
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-sm text-gray-700">Is List</span>
                      <span className="text-xs text-gray-400">(List[...])</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={field.is_optional || false}
                        onChange={(e) =>
                          handleUpdateField(index, { ...field, is_optional: e.target.checked })
                        }
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-sm text-gray-700">Is Optional</span>
                      <span className="text-xs text-gray-400">(Optional[...])</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) =>
                          handleUpdateField(index, { ...field, required: e.target.checked })
                        }
                        className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      <span className="text-sm text-gray-700">Required</span>
                    </label>
                  </div>

                  {/* Preview of final type */}
                  <div className="bg-gray-50 px-3 py-2 rounded mb-3">
                    <span className="text-xs text-gray-500">Final type: </span>
                    <code className="text-xs font-mono text-primary-600">
                      {buildFieldType(field)}
                    </code>
                  </div>

                  {/* Description */}
                  <input
                    type="text"
                    value={field.description || ''}
                    onChange={(e) =>
                      handleUpdateField(index, { ...field, description: e.target.value })
                    }
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-sm"
                    placeholder="Description (optional)"
                  />
                </div>
              ))}

              {formData.fields.length === 0 && (
                <p className="text-sm text-gray-500 text-center py-4">
                  No fields added yet. Click "Add Field" to add fields to this schema.
                </p>
              )}
            </div>
          </div>
        </form>

        <div className="px-6 py-4 border-t bg-gray-50 flex gap-3">
          <Button type="submit" onClick={handleSubmit} disabled={saving}>
            <Save className="w-4 h-4 mr-2" />
            {saving ? (isEditMode ? 'Updating...' : 'Creating...') : (isEditMode ? 'Update Schema' : 'Create Schema')}
          </Button>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
        </div>
      </div>
    </div>
  );
}

export default AddSchemaModal;
