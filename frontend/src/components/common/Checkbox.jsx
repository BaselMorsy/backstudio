function Checkbox({ label, checked, onChange, description }) {
  return (
    <div className="flex items-start mb-3">
      <div className="flex items-center h-5">
        <input
          type="checkbox"
          checked={checked}
          onChange={onChange}
          className="w-4 h-4 text-primary-600 bg-gray-100 border-gray-300 rounded focus:ring-primary-500 focus:ring-2"
        />
      </div>
      <div className="ml-3 text-sm">
        <label className="font-medium text-gray-700">{label}</label>
        {description && <p className="text-gray-500">{description}</p>}
      </div>
    </div>
  );
}

export default Checkbox;
