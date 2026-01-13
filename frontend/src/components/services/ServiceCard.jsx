import { useState } from 'react';
import { Edit2, Trash2, Box } from 'lucide-react';
import ConfirmDialog from '../common/ConfirmDialog';

function ServiceCard({ service, projectId, onClick, onDelete }) {
  const [confirmDelete, setConfirmDelete] = useState(false);

  return (
    <>
      <div className="card p-4 cursor-pointer hover:shadow-[0_0_0_3px_#c8a951] transition-all" onClick={onClick}>
        <div className="flex justify-between items-start mb-3">
          <div className="flex items-center gap-3">
            <div className="bg-primary-100 p-2 rounded-lg">
              <Box className="w-5 h-5 text-primary-600" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-800">{service.name}</h3>
              {service.description && (
                <p className="text-sm text-gray-500">{service.description}</p>
              )}
            </div>
          </div>
          <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={onClick}
              className="p-2 text-primary-600 hover:bg-primary-50 rounded transition-colors"
              title="Edit"
            >
              <Edit2 className="w-4 h-4" />
            </button>
            <button
              onClick={() => setConfirmDelete(true)}
              className="p-2 text-red-600 hover:bg-red-50 rounded transition-colors"
              title="Delete"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>

      <div className="grid grid-cols-3 gap-2 text-center text-sm">
        <div>
          <div className="font-semibold text-gray-800">{service.schemas?.length || 0}</div>
          <div className="text-gray-500 text-xs">Schemas</div>
        </div>
        <div>
          <div className="font-semibold text-gray-800">{service.functions?.length || 0}</div>
          <div className="text-gray-500 text-xs">Functions</div>
        </div>
        <div>
          <div className="font-semibold text-gray-800">{service.endpoints?.length || 0}</div>
          <div className="text-gray-500 text-xs">Endpoints</div>
        </div>
      </div>
    </div>

    <ConfirmDialog
      isOpen={confirmDelete}
      title="Delete Service"
      message={`Are you sure you want to delete service "${service.name}"? This action cannot be undone.`}
      confirmText="Delete"
      variant="danger"
      onConfirm={() => {
        onDelete(service.id);
        setConfirmDelete(false);
      }}
      onCancel={() => setConfirmDelete(false)}
    />
  </>
  );
}

export default ServiceCard;
