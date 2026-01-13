import { useState } from 'react';
import { Edit2, Trash2, Key } from 'lucide-react';
import ConfirmDialog from '../common/ConfirmDialog';

function ModelCard({ model, onEdit, onDelete }) {
  const primaryKeyField = model.fields?.find((f) => f.primary_key);
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <>
      <div
        className="card p-4 cursor-pointer hover:shadow-[0_0_0_3px_#c8a951] transition-all"
        onClick={() => onEdit(model)}
      >
        <div className="flex justify-between items-start mb-3">
          <div>
            <h3 className="text-lg font-semibold text-gray-800">{model.name}</h3>
            <p className="text-sm text-gray-500">{model.table_name}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEdit(model);
              }}
              className="p-2 text-primary-600 hover:bg-primary-50 rounded transition-colors"
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

      <div className="space-y-1 mb-3">
        {model.fields?.slice(0, 5).map((field) => (
          <div key={field.name} className="flex items-center justify-between text-sm">
            <div className="flex items-center gap-2">
              {field.primary_key && <Key className="w-3 h-3 text-yellow-500" />}
              <span className="text-gray-700">{field.name}</span>
            </div>
            <span className="text-gray-500 text-xs uppercase">{field.type}</span>
          </div>
        ))}
        {model.fields?.length > 5 && (
          <p className="text-xs text-gray-400 mt-2">+{model.fields.length - 5} more fields</p>
        )}
      </div>

      <div className="border-t pt-2">
        <p className="text-xs text-gray-500">{model.fields?.length || 0} fields</p>
      </div>
    </div>

    <ConfirmDialog
      isOpen={confirmDelete}
      title="Delete Model"
      message={`Are you sure you want to delete model "${model.name}"? This action cannot be undone.`}
      confirmText="Delete"
      variant="danger"
      onConfirm={() => {
        onDelete(model.id);
        setConfirmDelete(false);
      }}
      onCancel={() => setConfirmDelete(false)}
    />
  </>
  );
}

export default ModelCard;
