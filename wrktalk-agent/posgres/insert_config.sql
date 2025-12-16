INSERT INTO deployment_config (
    id, deployment_type, namespace, helm_release_name,
    smtp_host, smtp_port, smtp_user, smtp_password, smtp_from
) VALUES (
    uuid_generate_v4(),
    'kubernetes',
    'wrktalk',
    'wrktalk',
    'smtp.gmail.com',
    587,
    'mahimakesharwani1@gmail.com',
    'pymjschmdmbyxkpn',
    'mahimakesharwani1@gmail.com'
);

-- Insert admin user for email notifications
INSERT INTO admin (id, name, email, is_active, role) VALUES
    (uuid_generate_v4(), 'Admin User', 'mahimakesharwani1@gmail.com', true, 'ADMIN');