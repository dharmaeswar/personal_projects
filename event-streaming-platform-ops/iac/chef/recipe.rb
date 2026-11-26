# Broker host configuration — Chef recipe.
# Declarative only: validated by messaging.iac.check_chef_recipe
# and never converged against a real node by this project.
package 'openjdk-17-jre-headless' do
  action :install
end

user 'kafka' do
  system true
  shell '/usr/sbin/nologin'
  action :create
end

directory '/var/lib/kafka/data' do
  owner 'kafka'
  group 'kafka'
  mode '0750'
  recursive true
  action :create
end

directory '/etc/kafka' do
  owner 'kafka'
  group 'kafka'
  mode '0750'
  action :create
end

template '/etc/kafka/server.properties' do
  source 'server.properties.erb'
  owner 'kafka'
  group 'kafka'
  mode '0640'
  variables(
    broker_id: node['kafka']['broker_id'],
    listeners: node['kafka']['listeners'],
    log_dirs: '/var/lib/kafka/data'
  )
  notifies :restart, 'service[kafka]', :delayed
end

service 'kafka' do
  action [:enable, :start]
  supports restart: true, status: true
end
