import { useState } from 'react';
import { relationAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import { CARDINALITY_TYPES, LAZY_STRATEGIES, ON_DELETE_OPTIONS, CASCADE_OPTIONS } from '../../utils/constants';
import Modal from '../common/Modal';
import Input from '../common/Input';
import Select from '../common/Select';
import Button from '../common/Button';

function AddRelationModal({ projectId, models, relation, onClose, onSuccess }) {
  const toast = useToast();
  // Initialize form data from existing relation if editing
  const [formData, setFormData] = useState(() => {
    if (relation) {
      const sourceModel = models.find((m) => m.name === relation.source?.model);
      const targetModel = models.find((m) => m.name === relation.target?.model);

      return {
        name: relation.name || '',
        cardinality: relation.cardinality || 'one-to-many',
        sourceModel: sourceModel?.id || '',
        targetModel: targetModel?.id || '',

        // Source side configuration
        sourceAttribute: relation.source?.attribute || '',
        sourceLazy: relation.source?.lazy || 'select',
        sourceOrderBy: relation.source?.order_by || '',
        sourceViewonly: relation.source?.viewonly || false,

        // Target side configuration
        targetAttribute: relation.target?.attribute || '',
        targetLazy: relation.target?.lazy || 'select',
        targetOrderBy: relation.target?.order_by || '',
        targetViewonly: relation.target?.viewonly || false,

        // Foreign key configuration
        fkNullable: relation.foreign_key?.nullable ?? false,
        fkUnique: relation.foreign_key?.unique ?? false,
        fkOnDelete: relation.foreign_key?.ondelete || 'CASCADE',

        // Cascade behavior
        cascade: relation.behavior?.cascade || '',
        passiveDeletes: relation.behavior?.passive_deletes || false,
        passiveUpdates: relation.behavior?.passive_updates || false,
        enableTypechecks: relation.behavior?.enable_typechecks ?? true,

        // Association table (many-to-many)
        associationTableName: relation.association_table?.table_name || '',
      };
    }

    return {
      name: '',
      cardinality: 'one-to-many',
      sourceModel: '',
      targetModel: '',

      sourceAttribute: '',
      sourceLazy: 'select',
      sourceOrderBy: '',
      sourceViewonly: false,

      targetAttribute: '',
      targetLazy: 'select',
      targetOrderBy: '',
      targetViewonly: false,

      fkNullable: false,
      fkUnique: false,
      fkOnDelete: 'CASCADE',

      cascade: '',
      passiveDeletes: false,
      passiveUpdates: false,
      enableTypechecks: true,

      associationTableName: '',
    };
  });
  const [loading, setLoading] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(!!relation);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formData.name || !formData.sourceModel || !formData.targetModel) {
      toast.showWarning('Please fill in all required fields');
      return;
    }

    const sourceModel = models.find((m) => m.id === formData.sourceModel);
    const targetModel = models.find((m) => m.id === formData.targetModel);

    if (!sourceModel || !targetModel) {
      toast.showWarning('Please select both source and target models');
      return;
    }

    // Determine uselist based on cardinality
    const sourceUselist = formData.cardinality === 'one-to-many' || formData.cardinality === 'many-to-many';
    const targetUselist = formData.cardinality === 'many-to-one' || formData.cardinality === 'many-to-many';

    // Build relation data
    const relationData = {
      name: formData.name,
      cardinality: formData.cardinality,
      source: {
        model: sourceModel.name,
        attribute: formData.sourceAttribute || formData.name,
        uselist: sourceUselist,
        lazy: formData.sourceLazy,
        order_by: formData.sourceOrderBy || undefined,
        viewonly: formData.sourceViewonly,
      },
      target: {
        model: targetModel.name,
        attribute: formData.targetAttribute || `${sourceModel.name.toLowerCase()}_rel`,
        uselist: targetUselist,
        lazy: formData.targetLazy,
        order_by: formData.targetOrderBy || undefined,
        viewonly: formData.targetViewonly,
      },
    };

    // Add foreign key for non-many-to-many relations
    if (formData.cardinality !== 'many-to-many') {
      let fkModel, fkColumn, fkReferences;

      if (formData.cardinality === 'one-to-many') {
        // FK is on target (many) side
        fkModel = targetModel.name;
        fkColumn = `${sourceModel.name.toLowerCase()}_id`;
        fkReferences = `${sourceModel.table_name || sourceModel.name.toLowerCase() + 's'}.id`;
      } else if (formData.cardinality === 'many-to-one') {
        // FK is on source (many) side
        fkModel = sourceModel.name;
        fkColumn = `${targetModel.name.toLowerCase()}_id`;
        fkReferences = `${targetModel.table_name || targetModel.name.toLowerCase() + 's'}.id`;
      } else if (formData.cardinality === 'one-to-one') {
        // FK is on source side by default for one-to-one
        fkModel = sourceModel.name;
        fkColumn = `${targetModel.name.toLowerCase()}_id`;
        fkReferences = `${targetModel.table_name || targetModel.name.toLowerCase() + 's'}.id`;
      }

      relationData.foreign_key = {
        model: fkModel,
        column: fkColumn,
        references: fkReferences,
        nullable: formData.fkNullable,
        unique: formData.fkUnique,
        ondelete: formData.fkOnDelete,
      };
    } else {
      // Add association table for many-to-many
      if (formData.associationTableName) {
        relationData.association_table = {
          table_name: formData.associationTableName,
          left_foreign_key: {
            model: sourceModel.name,
            column: `${sourceModel.name.toLowerCase()}_id`,
            references: `${sourceModel.table_name || sourceModel.name.toLowerCase() + 's'}.id`,
            nullable: false,
            ondelete: 'CASCADE',
          },
          right_foreign_key: {
            model: targetModel.name,
            column: `${targetModel.name.toLowerCase()}_id`,
            references: `${targetModel.table_name || targetModel.name.toLowerCase() + 's'}.id`,
            nullable: false,
            ondelete: 'CASCADE',
          },
        };
      }
    }

    // Add cascade behavior if specified
    if (formData.cascade || formData.passiveDeletes || formData.passiveUpdates || !formData.enableTypechecks) {
      relationData.behavior = {
        cascade: formData.cascade || undefined,
        passive_deletes: formData.passiveDeletes,
        passive_updates: formData.passiveUpdates,
        enable_typechecks: formData.enableTypechecks,
      };
    }

    try {
      setLoading(true);

      if (relation) {
        // Update existing relation
        await relationAPI.update(projectId, formData.sourceModel, relation.id, relationData);
        toast.showSuccess('Relationship updated successfully');
      } else {
        // Create new relation
        await relationAPI.create(projectId, formData.sourceModel, relationData);
        toast.showSuccess('Relationship created successfully');
      }

      onSuccess();
    } catch (error) {
      console.error(`Failed to ${relation ? 'update' : 'create'} relation:`, error);
      toast.showError(error.response?.data?.detail || `Failed to ${relation ? 'update' : 'create'} relationship`);
    } finally {
      setLoading(false);
    }
  };

  const isManyToMany = formData.cardinality === 'many-to-many';

  return (
    <Modal isOpen={true} onClose={onClose} title={relation ? "Edit Relationship" : "Create Relationship"}>
      <form onSubmit={handleSubmit} className="space-y-4 max-h-[calc(100vh-200px)] overflow-y-auto">
        {/* Basic Information */}
        <div className="space-y-4 pb-4 border-b">
          <h3 className="text-sm font-semibold text-gray-700">Basic Information</h3>

          <Input
            label="Relationship Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            placeholder="user_posts"
            required
          />

          <Select
            label="Cardinality"
            value={formData.cardinality}
            onChange={(e) => setFormData({ ...formData, cardinality: e.target.value })}
            options={CARDINALITY_TYPES}
            required
          />

          <Select
            label="Source Model"
            value={formData.sourceModel}
            onChange={(e) => setFormData({ ...formData, sourceModel: e.target.value })}
            options={models.map((m) => ({ value: m.id, label: m.name }))}
            placeholder="Select source model"
            required
          />

          <Select
            label="Target Model"
            value={formData.targetModel}
            onChange={(e) => setFormData({ ...formData, targetModel: e.target.value })}
            options={models.map((m) => ({ value: m.id, label: m.name }))}
            placeholder="Select target model"
            required
          />
        </div>

        {/* Advanced Options Toggle */}
        <div className="pb-4 border-b">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-sm text-primary-600 hover:text-primary-700 font-medium"
          >
            {showAdvanced ? '▼' : '▶'} Advanced Configuration
          </button>
        </div>

        {showAdvanced && (
          <>
            {/* Source Side Configuration */}
            <div className="space-y-4 pb-4 border-b">
              <h3 className="text-sm font-semibold text-gray-700">Source Side Configuration</h3>

              <Input
                label="Source Attribute Name"
                value={formData.sourceAttribute}
                onChange={(e) => setFormData({ ...formData, sourceAttribute: e.target.value })}
                placeholder="Auto-generated if empty"
              />

              <Select
                label="Source Lazy Loading Strategy"
                value={formData.sourceLazy}
                onChange={(e) => setFormData({ ...formData, sourceLazy: e.target.value })}
                options={LAZY_STRATEGIES.map((s) => ({ value: s, label: s }))}
              />

              <Input
                label="Source Order By (optional)"
                value={formData.sourceOrderBy}
                onChange={(e) => setFormData({ ...formData, sourceOrderBy: e.target.value })}
                placeholder="e.g., created_at DESC"
              />

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="sourceViewonly"
                  checked={formData.sourceViewonly}
                  onChange={(e) => setFormData({ ...formData, sourceViewonly: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <label htmlFor="sourceViewonly" className="text-sm text-gray-700">
                  View Only (read-only relationship)
                </label>
              </div>
            </div>

            {/* Target Side Configuration */}
            <div className="space-y-4 pb-4 border-b">
              <h3 className="text-sm font-semibold text-gray-700">Target Side Configuration</h3>

              <Input
                label="Target Attribute Name"
                value={formData.targetAttribute}
                onChange={(e) => setFormData({ ...formData, targetAttribute: e.target.value })}
                placeholder="Auto-generated if empty"
              />

              <Select
                label="Target Lazy Loading Strategy"
                value={formData.targetLazy}
                onChange={(e) => setFormData({ ...formData, targetLazy: e.target.value })}
                options={LAZY_STRATEGIES.map((s) => ({ value: s, label: s }))}
              />

              <Input
                label="Target Order By (optional)"
                value={formData.targetOrderBy}
                onChange={(e) => setFormData({ ...formData, targetOrderBy: e.target.value })}
                placeholder="e.g., name ASC"
              />

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="targetViewonly"
                  checked={formData.targetViewonly}
                  onChange={(e) => setFormData({ ...formData, targetViewonly: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <label htmlFor="targetViewonly" className="text-sm text-gray-700">
                  View Only (read-only relationship)
                </label>
              </div>
            </div>

            {/* Foreign Key Configuration (not for many-to-many) */}
            {!isManyToMany && (
              <div className="space-y-4 pb-4 border-b">
                <h3 className="text-sm font-semibold text-gray-700">Foreign Key Configuration</h3>

                <Select
                  label="On Delete Behavior"
                  value={formData.fkOnDelete}
                  onChange={(e) => setFormData({ ...formData, fkOnDelete: e.target.value })}
                  options={ON_DELETE_OPTIONS.map((o) => ({ value: o, label: o }))}
                />

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="fkNullable"
                    checked={formData.fkNullable}
                    onChange={(e) => setFormData({ ...formData, fkNullable: e.target.checked })}
                    className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                  />
                  <label htmlFor="fkNullable" className="text-sm text-gray-700">
                    Nullable (allow NULL values)
                  </label>
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="fkUnique"
                    checked={formData.fkUnique}
                    onChange={(e) => setFormData({ ...formData, fkUnique: e.target.checked })}
                    className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                  />
                  <label htmlFor="fkUnique" className="text-sm text-gray-700">
                    Unique (enforce unique constraint)
                  </label>
                </div>
              </div>
            )}

            {/* Association Table (many-to-many only) */}
            {isManyToMany && (
              <div className="space-y-4 pb-4 border-b">
                <h3 className="text-sm font-semibold text-gray-700">Association Table Configuration</h3>

                <Input
                  label="Association Table Name"
                  value={formData.associationTableName}
                  onChange={(e) => setFormData({ ...formData, associationTableName: e.target.value })}
                  placeholder="Auto-generated if empty"
                />
                <p className="text-xs text-gray-500 -mt-2">
                  Default: {formData.sourceModel && formData.targetModel
                    ? `${models.find(m => m.id === formData.sourceModel)?.name.toLowerCase() || 'source'}_${models.find(m => m.id === formData.targetModel)?.name.toLowerCase() || 'target'}`
                    : 'source_target'}
                </p>
              </div>
            )}

            {/* Cascade Behavior */}
            <div className="space-y-4 pb-4 border-b">
              <h3 className="text-sm font-semibold text-gray-700">Cascade Behavior</h3>

              <Select
                label="Cascade Strategy"
                value={formData.cascade}
                onChange={(e) => setFormData({ ...formData, cascade: e.target.value })}
                options={[{ value: '', label: 'None' }, ...CASCADE_OPTIONS]}
              />

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="passiveDeletes"
                  checked={formData.passiveDeletes}
                  onChange={(e) => setFormData({ ...formData, passiveDeletes: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <label htmlFor="passiveDeletes" className="text-sm text-gray-700">
                  Passive Deletes (rely on DB CASCADE)
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="passiveUpdates"
                  checked={formData.passiveUpdates}
                  onChange={(e) => setFormData({ ...formData, passiveUpdates: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <label htmlFor="passiveUpdates" className="text-sm text-gray-700">
                  Passive Updates (rely on DB UPDATE)
                </label>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="enableTypechecks"
                  checked={formData.enableTypechecks}
                  onChange={(e) => setFormData({ ...formData, enableTypechecks: e.target.checked })}
                  className="w-4 h-4 text-primary-600 border-gray-300 rounded focus:ring-primary-500"
                />
                <label htmlFor="enableTypechecks" className="text-sm text-gray-700">
                  Enable Type Checks (recommended)
                </label>
              </div>
            </div>
          </>
        )}

        {/* Action Buttons */}
        <div className="flex justify-end gap-3 pt-4 border-t sticky bottom-0 bg-white">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={loading}>
            {loading
              ? relation ? 'Updating...' : 'Creating...'
              : relation ? 'Update Relationship' : 'Create Relationship'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export default AddRelationModal;
