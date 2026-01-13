import { useNavigate } from 'react-router-dom';
import { Code2, Database, Zap, Box, ArrowRight, Sparkles } from 'lucide-react';
import AnimatedLogo from '../components/AnimatedLogo';

function LandingPage() {
  const navigate = useNavigate();

  const features = [
    {
      icon: <Database className="w-8 h-8" />,
      title: 'Visual Data Modeling',
      description: 'Define database models, fields, and relationships through an intuitive UI',
    },
    {
      icon: <Box className="w-8 h-8" />,
      title: 'Service Architecture',
      description: 'Design services, schemas, functions, and API endpoints with complete control',
    },
    {
      icon: <Zap className="w-8 h-8" />,
      title: 'FastAPI Code Generation',
      description: 'Generate production-ready Python FastAPI code with SQLAlchemy and Pydantic',
    },
    {
      icon: <Code2 className="w-8 h-8" />,
      title: 'Dependency Injection',
      description: 'Configure guards and providers for authentication, authorization, and more',
    },
    {
      icon: <Sparkles className="w-8 h-8" />,
      title: 'MCP Server',
      description: 'Describe your backend in natural language—AI translates your specs into a fully structured project',
    },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-800 via-primary-700 to-primary-900 flex items-center">
      {/* Hero Section */}
      <div className="container mx-auto px-8 py-12">
        <div className="text-center mb-10">
          {/* Logo */}
          <div className="flex justify-center mb-5">
            <AnimatedLogo />
          </div>

          <p className="text-xl mb-4 text-accent-mutedGold uppercase tracking-[0.15em] font-serif">
            Build with Specs, Not Intent
          </p>
          <p className="text-base text-primary-100 max-w-3xl mx-auto mb-8 leading-relaxed">
            Design, configure, and generate production-ready backend applications
            with a visual interface. No more boilerplate—focus on what matters.
          </p>
          <button
            onClick={() => navigate('/dashboard')}
            className="bg-accent-gold text-primary-800 hover:bg-primary-300 font-semibold py-3 px-8 rounded-lg text-base transition-all transform hover:scale-105 shadow-lg inline-flex items-center gap-2"
          >
            Get Started
            <ArrowRight className="w-5 h-5" />
          </button>
        </div>

        {/* Features Grid */}
        <div className="grid md:grid-cols-2 lg:grid-cols-5 gap-5 mt-12">
          {features.map((feature, index) => (
            <div
              key={index}
              className="bg-primary-900 bg-opacity-40 backdrop-blur-sm border border-accent-gold border-opacity-20 rounded-xl p-5 hover:border-opacity-40 hover:bg-opacity-60 transition-all"
            >
              <div className="text-accent-gold mb-3">{feature.icon}</div>
              <h3 className="text-lg font-semibold text-accent-ivory mb-2">
                {feature.title}
              </h3>
              <p className="text-sm text-primary-100 leading-snug">{feature.description}</p>
            </div>
          ))}
        </div>

        {/* Additional Info */}
        <div className="mt-10 text-center text-accent-mutedGold">
          <p className="text-sm tracking-wider">
            Built with modern best practices · Type-safe · Fully customizable
          </p>
        </div>
      </div>
    </div>
  );
}

export default LandingPage;
