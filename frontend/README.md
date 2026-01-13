<div align="center">
  <img src="../assets/logo.svg" alt="BackStudio Logo" width="150"/>

  # BackStudio Frontend

  **Visual Backend Designer - React UI**
</div>

## Overview

The BackStudio frontend is a modern React-based web interface for visually designing backend applications. It provides an intuitive UI for defining data models, services, endpoints, and dependencies without writing code.

## Features

- **Project Dashboard** - Manage multiple backend projects
- **Visual Model Designer** - Create database models with drag-and-drop interface
- **Service Builder** - Define services and business logic functions
- **Endpoint Designer** - Configure REST API endpoints with HTTP methods and parameters
- **Dependency Manager** - Set up authentication guards and data providers
- **Real-time Preview** - See your backend structure as you build
- **Code Generation** - One-click generation of FastAPI code
- **Modern UI** - Built with React 18, Tailwind CSS, and Lucide Icons

## Installation

### Prerequisites
- Node.js 16 or higher
- npm or yarn

### Install Dependencies
```bash
cd BackStudio/frontend
npm install
```

## Running the Application

### Development Mode
```bash
npm run dev
```

The app will be available at http://localhost:5173

### Production Build
```bash
npm run build
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── common/            # Reusable UI components
│   │   │   ├── Button.jsx
│   │   │   ├── Input.jsx
│   │   │   └── Card.jsx
│   │   ├── layout/            # Layout components
│   │   │   ├── Header.jsx
│   │   │   ├── Sidebar.jsx
│   │   │   └── Layout.jsx
│   │   ├── modals/            # Modal dialogs
│   │   │   ├── AddModelModal.jsx
│   │   │   ├── AddServiceModal.jsx
│   │   │   ├── AddEndpointModal.jsx
│   │   │   └── EditDependencyModal.jsx
│   │   └── pages/             # Page components
│   │       ├── ProjectsPage.jsx
│   │       ├── ModelsPage.jsx
│   │       ├── ServicesPage.jsx
│   │       ├── EndpointsPage.jsx
│   │       └── DependenciesPage.jsx
│   ├── services/
│   │   └── api.js             # API client for backend
│   ├── utils/
│   │   └── constants.js       # Constants and configurations
│   ├── App.jsx                # Main app component
│   └── main.jsx               # Entry point
├── public/                    # Static assets
├── index.html                 # HTML template
├── package.json               # Dependencies
├── vite.config.js             # Vite configuration
└── tailwind.config.js         # Tailwind CSS configuration
```

## Features Guide

### Creating a Project
1. Click "New Project" on the dashboard
2. Fill in project details (name, description, database type)
3. Configure JWT authentication settings
4. Click "Create Project"

### Designing Data Models
1. Navigate to the "Models" tab
2. Click "Add Model"
3. Define fields with types and constraints
4. Set up relationships (One-to-Many, Many-to-Many)
5. Save the model

### Creating Services
1. Go to the "Services" tab
2. Click "Add Service"
3. Define service methods with parameters
4. Create DTOs for request/response schemas
5. Save the service

### Configuring Endpoints
1. Open the "Endpoints" tab
2. Click "Add Endpoint"
3. Select HTTP method and path
4. Map to a service function
5. Configure parameters and schemas
6. Add dependencies (guards/providers)
7. Save the endpoint

### Managing Dependencies
1. Visit the "Dependencies" tab
2. Create guards for authentication
3. Add providers for data injection
4. Configure return types and field extraction
5. Use in endpoints

## API Integration

The frontend communicates with the backend via REST API:

```javascript
// Example: Creating a model
import { modelAPI } from './services/api';

const newModel = await modelAPI.create(projectId, {
  name: 'User',
  table_name: 'users',
  fields: [
    { name: 'id', type: 'integer', primary_key: true },
    { name: 'email', type: 'string', max_length: 255 }
  ]
});
```

## Customization

### Theming
Modify `tailwind.config.js` to customize colors and styles:

```javascript
module.exports = {
  theme: {
    extend: {
      colors: {
        primary: {
          500: '#your-color',
          // ...
        }
      }
    }
  }
}
```

### Adding Components
Create new components in `src/components/` following the existing structure.

## Development

### Code Quality
```bash
# Format code
npm run format

# Lint code
npm run lint

# Type check (if using TypeScript)
npm run type-check
```

### Building for Production
```bash
npm run build
```

Output will be in the `dist/` directory.

## Troubleshooting

### Port Already in Use
```bash
# Kill process on port 5173
lsof -ti:5173 | xargs kill -9
```

### Dependencies Not Installing
```bash
# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

### API Connection Issues
Check that the backend is running on http://localhost:8000

## Technology Stack

- **React 18** - UI library
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Utility-first CSS framework
- **Lucide React** - Icon library
- **Axios** - HTTP client

## License

MIT License - see LICENSE file for details.

---

<div align="center">
  Part of the BackStudio Project
</div>
