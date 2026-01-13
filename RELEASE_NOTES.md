# 🎉 BackStudio v1.0.0 - Initial Release

**Visual Backend Code Generator - Build FastAPI backends through an intuitive UI**

BackStudio is a powerful visual backend code generator that lets you design and build production-ready FastAPI backends through an intuitive web interface. Define your data models, services, endpoints, and dependencies visually, then generate clean, deterministic Python code ready for deployment.

---

## ✨ Key Features

- **Visual Design Interface** - Build your backend architecture through an intuitive React-based UI
- **Model-First Approach** - Define database models with relationships, validations, and constraints
- **Service Architecture** - Create modular services with custom business logic
- **Endpoint Designer** - Configure REST API endpoints with proper HTTP methods, parameters, and schemas
- **Dependency Injection** - Set up guards (auth/validation) and providers (data injection) visually
- **Deterministic Code Generation** - Same specs = same code, guaranteed by SHA256 checksums
- **Complete Specification Model** - Define data models, relationships, services, endpoints, middlewares, and dependencies
- **Service-Oriented Architecture** - Generated code provides complete boilerplate - you only write service function bodies
- **State Management** - Project state stored as JSON with checksum validation
- **Template-Based** - Uses Jinja2 templates for flexible, customizable code generation
- **Multiple Databases** - Support for PostgreSQL, MySQL, SQLite, and MongoDB
- **JWT Authentication** - Built-in JWT auth with customizable token configuration
- **API Documentation** - Auto-generated OpenAPI/Swagger docs
- **MCP Server Support** - Extend functionality through Model Context Protocol

---

## 📋 Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.11 or higher** - [Download Python](https://www.python.org/downloads/)
- **Node.js 16 or higher** - [Download Node.js](https://nodejs.org/)
- **Package Manager** - Choose one:
  - [uv](https://docs.astral.sh/uv/) (recommended for speed)
  - pip (comes with Python)
  - [Conda/Miniconda](https://docs.conda.io/en/latest/miniconda.html)

---

## 🚀 Quick Start

### **Linux/macOS**

```bash
# Clone the repository
git clone https://github.com/BaselMorsy/backstudio.git
cd backstudio

# Run setup script (installs dependencies)
chmod +x setup.sh
./setup.sh

# Start BackStudio
./start.sh
```

### **Windows**

```cmd
# Clone the repository
git clone https://github.com/BaselMorsy/backstudio.git
cd backstudio

# Run setup script
setup.bat

# Start BackStudio
start.bat
```

---

## 🌐 Access Points

After starting BackStudio, you can access:

- **Frontend UI**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative Docs**: http://localhost:8000/redoc

---

## 📦 What's Included

### **Backend** (FastAPI Code Generation Engine)
- REST API endpoints for project management
- Pydantic schemas for validation
- Business logic services
- Jinja2 code templates
- Checksum-based deterministic generation

### **Frontend** (React Visual Designer)
- Intuitive UI components for visual design
- API clients for backend communication
- Helper utilities

### **MCP Server** (Model Context Protocol)
- Extensibility support

### **Scripts**
- Automated setup scripts for Linux/macOS/Windows
- Start/stop scripts for easy management

---

## 🎯 Usage Example

1. **Create a Project** via API or UI
2. **Define Data Models** with fields, types, and relationships
3. **Create Services** for business logic
4. **Configure Database** connection settings
5. **Generate Code** - Get production-ready FastAPI code
6. **Download & Deploy** - ZIP download or direct deployment

---

## 🏗️ Architecture

The generated backends follow a clean, modular architecture:

```
Generated Project/
├── models/          # SQLAlchemy ORM models
├── schemas/         # Pydantic validation schemas
├── services/        # Business logic layer
├── api/             # REST API routes
├── config/          # Configuration management
└── main.py          # Application entry point
```

---

## 🔒 Security Features

- JWT-based authentication
- Environment variable configuration
- Secure password hashing
- CORS configuration
- Input validation via Pydantic

---

## 📚 Documentation

Full documentation is available in the [README.md](README.md) file, including:
- Complete API endpoint reference
- Detailed usage examples
- Configuration options
- Development workflow guide
- Checksum system explanation

---

## 🛠️ Supported Frameworks

**Current Release:**
- FastAPI (Python) - Full support

**Planned:**
- Express.js (Node/JavaScript)
- NestJS (Node/TypeScript)
- Next.js (React/TypeScript)

---

## 🐛 Known Limitations

- Template system is currently basic (comprehensive Jinja2 templates coming soon)
- Database migrations not yet auto-generated
- GraphQL and WebSocket support planned for future releases

---

## 🤝 Contributing

Contributions are welcome! Please see the [README](README.md) for contribution guidelines.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

---

## 🙏 Support

For issues, questions, or suggestions:
- Open an issue at: https://github.com/BaselMorsy/backstudio/issues
- Check the documentation in README.md

---

**BackStudio** - Generate once, deploy anywhere. Same specs, same code, guaranteed.

🤖 *Built with passion for developers who want to focus on business logic, not boilerplate.*
