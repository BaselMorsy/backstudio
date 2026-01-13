import { useState } from 'react';
import { Trash2, ArrowRight, Edit2 } from 'lucide-react';
import ConfirmDialog from '../common/ConfirmDialog';

function RelationCard({ relation, models, onDelete, onEdit }) {
  const sourceModel = models.find((m) => m.name === relation.source?.model);
  const targetModel = models.find((m) => m.name === relation.target?.model);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const cardinalityLabel = {
    'one-to-many': '1:N',
    'many-to-one': 'N:1',
    'one-to-one': '1:1',
    'many-to-many': 'N:N',
  };

  return (
    <>
      <div
        className="card p-4 hover:shadow-[0_0_0_3px_#c8a951] transition-all cursor-pointer"
        onClick={() => onEdit && onEdit(relation)}
      >
        <div className="flex justify-between items-start mb-3">
          <div>
            <h3 className="text-lg font-semibold text-gray-800">{relation.name}</h3>
            <p className="text-sm text-primary-600 font-semibold">{cardinalityLabel[relation.cardinality]}</p>
          </div>
          <div className="flex gap-1">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit && onEdit(relation);
              }}
              className="p-2 text-blue-600 hover:bg-blue-50 rounded transition-colors"
              title="Edit"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setConfirmDelete(true);
              }}
              className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

      <div className="flex items-center gap-3 text-sm mb-3">
        <div className="bg-primary-50 px-3 py-2 rounded font-medium text-primary-700">
          {relation.source?.model}
        </div>
        <ArrowRight className="w-4 h-4 text-gray-400" />
        <div className="bg-green-50 px-3 py-2 rounded font-medium text-green-700">
          {relation.target?.model}
        </div>
      </div>

      {/* Detailed Information */}
      <div className="space-y-2 text-xs">
        {/* Foreign Key Info */}
        {relation.foreign_key && (
          <div className="bg-gray-50 p-2 rounded">
            <div className="font-semibold text-gray-700 mb-1">Foreign Key:</div>
            <div className="text-gray-600">
              <span className="font-mono">{relation.foreign_key.column}</span>
              {' → '}
              <span className="font-mono">{relation.foreign_key.references}</span>
            </div>
            <div className="text-gray-500 mt-1">
              On Delete: <span className="font-semibold">{relation.foreign_key.ondelete || 'NO ACTION'}</span>
              {' | '}
              Nullable: <span className="font-semibold">{relation.foreign_key.nullable ? 'Yes' : 'No'}</span>
            </div>
          </div>
        )}

        {/* Association Table (Many-to-Many) */}
        {relation.association_table && (
          <div className="bg-purple-50 p-2 rounded">
            <div className="font-semibold text-purple-700 mb-1">Association Table:</div>
            <div className="text-purple-600 font-mono">{relation.association_table.table_name}</div>
          </div>
        )}

        {/* Cascade Behavior */}
        {relation.behavior && (
          <div className="bg-orange-50 p-2 rounded">
            <div className="font-semibold text-orange-700 mb-1">Cascade Behavior:</div>
            <div className="text-orange-600">
              {relation.behavior.cascade && (
                <div>Cascade: <span className="font-semibold">{relation.behavior.cascade}</span></div>
              )}
              {relation.behavior.passive_deletes !== undefined && (
                <div>Passive Deletes: <span className="font-semibold">{relation.behavior.passive_deletes ? 'Yes' : 'No'}</span></div>
              )}
            </div>
          </div>
        )}

        {/* Lazy Loading */}
        <div className="bg-blue-50 p-2 rounded">
          <div className="font-semibold text-blue-700 mb-1">Lazy Loading:</div>
          <div className="text-blue-600">
            Source: <span className="font-semibold">{relation.source?.lazy || 'select'}</span>
            {' | '}
            Target: <span className="font-semibold">{relation.target?.lazy || 'select'}</span>
          </div>
        </div>
      </div>
    </div>

    <ConfirmDialog
      isOpen={confirmDelete}
      title="Delete Relationship"
      message={`Are you sure you want to delete relationship "${relation.name}"? This action cannot be undone.`}
      confirmText="Delete"
      variant="danger"
      onConfirm={() => {
        onDelete(sourceModel?.id || models[0]?.id, relation.id);
        setConfirmDelete(false);
      }}
      onCancel={() => setConfirmDelete(false)}
    />
  </>
  );
}

export default RelationCard;
