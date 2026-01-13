import { useState, useEffect } from 'react';
import { Plus, Boxes } from 'lucide-react';
import { serviceAPI } from '../../services/api';
import { useToast } from '../common/ToastContainer';
import Button from '../common/Button';
import ServiceCard from '../services/ServiceCard';
import AddServiceModal from '../modals/AddServiceModal';
import ServiceDetailModal from '../modals/ServiceDetailModal';

function ServicesTab({ projectId }) {
  const toast = useToast();
  const [services, setServices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedService, setSelectedService] = useState(null);

  useEffect(() => {
    fetchServices();
  }, [projectId]);

  const fetchServices = async () => {
    try {
      setLoading(true);
      const response = await serviceAPI.getAll(projectId);
      setServices(response.data);
    } catch (error) {
      console.error('Failed to fetch services:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteService = async (serviceId) => {
    try {
      await serviceAPI.delete(projectId, serviceId);
      setServices(services.filter((s) => s.id !== serviceId));
      toast.showSuccess('Service deleted successfully');
    } catch (error) {
      console.error('Failed to delete service:', error);
      toast.showError(error.response?.data?.detail || 'Failed to delete service');
    }
  };

  const handleUpdateService = (updatedService) => {
    setServices(services.map((s) => (s.id === updatedService.id ? updatedService : s)));
  };

  if (loading) {
    return <div className="text-center py-10">Loading...</div>;
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-2">
          <Boxes className="w-5 h-5 text-gray-600" />
          <h2 className="text-2xl font-bold text-gray-800">Services</h2>
          <span className="bg-gray-200 text-gray-700 px-2 py-1 rounded-full text-sm">
            {services.length}
          </span>
        </div>
        <Button onClick={() => setShowAddModal(true)} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Service
        </Button>
      </div>

      {services.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-lg border-2 border-dashed border-gray-300">
          <Boxes className="w-12 h-12 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-500 mb-4">No services defined yet</p>
          <Button onClick={() => setShowAddModal(true)} className="inline-flex items-center gap-2">
            <Plus className="w-4 h-4" />
            Add Your First Service
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {services.map((service) => (
            <ServiceCard
              key={service.id}
              service={service}
              projectId={projectId}
              onClick={() => setSelectedService(service)}
              onDelete={handleDeleteService}
            />
          ))}
        </div>
      )}

      {showAddModal && (
        <AddServiceModal
          projectId={projectId}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            fetchServices();
            setShowAddModal(false);
          }}
        />
      )}

      {selectedService && (
        <ServiceDetailModal
          service={selectedService}
          projectId={projectId}
          onClose={() => setSelectedService(null)}
          onUpdate={handleUpdateService}
        />
      )}
    </div>
  );
}

export default ServicesTab;
