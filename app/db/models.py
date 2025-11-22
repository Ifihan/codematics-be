from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Table, BigInteger, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.database import Base


user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey('roles.id'), primary_key=True)
)


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    permissions = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    github_token = Column(String, nullable=True)
    github_refresh_token = Column(String(512), nullable=True)
    github_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    github_username = Column(String, nullable=True)

    roles = relationship("Role", secondary=user_roles, backref="users")


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class Notebook(Base):
    __tablename__ = "notebooks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default="uploaded")
    main_py_path = Column(String, nullable=True)
    requirements_txt_path = Column(String, nullable=True)
    dependencies = Column(JSON, nullable=True)
    code_cells_count = Column(Integer, nullable=True)
    syntax_valid = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    parsed_at = Column(DateTime(timezone=True), nullable=True)


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True, index=True)
    notebook_id = Column(Integer, ForeignKey("notebooks.id"), unique=True, nullable=False)
    health_score = Column(Integer, nullable=False)
    cell_classifications = Column(JSON, nullable=False)
    issues = Column(JSON, nullable=False)
    recommendations = Column(JSON, nullable=True)
    resource_estimates = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(Integer, primary_key=True, index=True)
    notebook_id = Column(Integer, ForeignKey("notebooks.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, default="pending")
    build_id = Column(String, nullable=True)
    image_url = Column(String, nullable=True)
    service_url = Column(String, nullable=True)
    region = Column(String, nullable=False)
    dockerfile_path = Column(String, nullable=True)
    source_gcs_uri = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    build_logs_url = Column(String, nullable=True)
    build_duration = Column(Integer, nullable=True)
    admin_api_key = Column(String, nullable=True)
    github_repo_url = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    deployed_at = Column(DateTime(timezone=True), nullable=True)


class DeploymentMetric(Base):
    __tablename__ = "deployment_metrics"

    id = Column(Integer, primary_key=True, index=True)
    deployment_id = Column(Integer, ForeignKey("deployments.id"), nullable=False)
    metric_type = Column(String, nullable=False)
    value = Column(JSON, nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now())


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, index=True)
    notebook_id = Column(Integer, ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    gcs_path = Column(String(512), nullable=False)
    size_bytes = Column(BigInteger, nullable=True)
    accuracy = Column(Numeric(5, 2), nullable=True)
    is_active = Column(Boolean, default=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())