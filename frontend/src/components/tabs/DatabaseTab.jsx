import { useState, useEffect } from 'react';
import { Plus, Database, Link as LinkIcon } from 'lucide-react';
import { modelAPI, relationAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import ModelCard from '../database/ModelCard';
import RelationCard from '../database/RelationCard';
import AddModelModal from '../modals/AddModelModal';
import AddRelationModal from '../modals/AddRelationModal';

function DatabaseTab({ projectId }) {
  const toast = useToast();
  const [models, setModels] = useState([]);
  const [relations, setRelations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModelModal, setShowModelModal] = useState(false);
  const [showRelationModal, setShowRelationModal] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [editingRelation, setEditingRelation] = useState(null);

  useEffect(() => {
    fetchData();
  }, [projectId]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const modelsResponse = await modelAPI.getAll(projectId);
      setModels(modelsResponse.data);

      // Fetch relations for all models and deduplicate by ID
      const allRelations = [];
      const relationIds = new Set();

      for (const model of modelsResponse.data) {
        try {
          const relationsResponse = await relationAPI.getAll(projectId, model.id);

          // Only add relations we haven't seen before
          for (const relation of relationsResponse.data) {
            if (!relationIds.has(relation.id)) {
              relationIds.add(relation.id);
              allRelations.push(relation);
            }
          }
        } catch (error) {
          console.error(`Failed to fetch relations for model ${model.id}:`, error);
        }
      }
      setRelations(allRelations);
    } catch (error) {
      console.error('Failed to fetch database data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteModel = async (modelId) => {
    try {
      await modelAPI.delete(projectId, modelId);
      setModels(models.filter((m) => m.id !== modelId));
      toast.showSuccess('Model deleted successfully');
    } catch (error) {
      console.error('Failed to delete model:', error);
      toast.showError(error.response?.data?.detail || 'Failed to delete model');
    }
  };

  const handleDeleteRelation = async (modelId, relationId) => {
    try {
      await relationAPI.delete(projectId, modelId, relationId);
      setRelations(relations.filter((r) => r.id !== relationId));
      toast.showSuccess('Relationship deleted successfully');
    } catch (error) {
      console.error('Failed to delete relation:', error);
      toast.showError(error.response?.data?.detail || 'Failed to delete relation');
    }
  };

  if (loading) {
    return <div className="text-center py-10">Loading...</div>;
  }

  return (
    <div className="space-y-8">
      {/* Data Models Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-gray-600" />
            <h2 className="text-2xl font-bold text-gray-800">Data Models</h2>
            <span className="bg-gray-200 text-gray-700 px-2 py-1 rounded-full text-sm">
              {models.length}
            </span>
          </div>
          <Button onClick={() => setShowModelModal(true)} className="flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Add Model
          </Button>
        </div>

        {models.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border-2 border-dashed border-gray-300">
            <Database className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-500 mb-4">No data models defined yet</p>
            <Button onClick={() => setShowModelModal(true)} className="inline-flex items-center gap-2">
              <Plus className="w-4 h-4" />
              Add Your First Model
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {models.map((model) => (
              <ModelCard
                key={model.id}
                model={model}
                onEdit={(model) => {
                  setEditingModel(model);
                  setShowModelModal(true);
                }}
                onDelete={handleDeleteModel}
              />
            ))}
          </div>
        )}
      </div>

      {/* Relations Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-2">
            <LinkIcon className="w-5 h-5 text-gray-600" />
            <h2 className="text-2xl font-bold text-gray-800">Relationships</h2>
            <span className="bg-gray-200 text-gray-700 px-2 py-1 rounded-full text-sm">
              {relations.length}
            </span>
          </div>
          <Button
            onClick={() => setShowRelationModal(true)}
            className="flex items-center gap-2"
            disabled={models.length < 2}
          >
            <Plus className="w-4 h-4" />
            Add Relationship
          </Button>
        </div>

        {relations.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-lg border-2 border-dashed border-gray-300">
            <LinkIcon className="w-12 h-12 text-gray-400 mx-auto mb-3" />
            <p className="text-gray-500 mb-4">
              {models.length < 2
                ? 'Create at least 2 models to define relationships'
                : 'No relationships defined yet'}
            </p>
            {models.length >= 2 && (
              <Button onClick={() => setShowRelationModal(true)} className="inline-flex items-center gap-2">
                <Plus className="w-4 h-4" />
                Add Your First Relationship
              </Button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {relations.map((relation) => (
              <RelationCard
                key={relation.id}
                relation={relation}
                models={models}
                onDelete={handleDeleteRelation}
                onEdit={(relation) => {
                  setEditingRelation(relation);
                  setShowRelationModal(true);
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {showModelModal && (
        <AddModelModal
          projectId={projectId}
          model={editingModel}
          onClose={() => {
            setShowModelModal(false);
            setEditingModel(null);
          }}
          onSuccess={() => {
            fetchData();
            setShowModelModal(false);
            setEditingModel(null);
          }}
        />
      )}

      {showRelationModal && (
        <AddRelationModal
          projectId={projectId}
          models={models}
          relation={editingRelation}
          onClose={() => {
            setShowRelationModal(false);
            setEditingRelation(null);
          }}
          onSuccess={() => {
            fetchData();
            setShowRelationModal(false);
            setEditingRelation(null);
          }}
        />
      )}
    </div>
  );
}

export default DatabaseTab;
