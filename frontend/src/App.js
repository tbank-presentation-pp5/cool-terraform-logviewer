import React from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  UploadOutlined,
  DashboardOutlined,
  BarChartOutlined,
  TrophyOutlined
} from '@ant-design/icons';
import LogUploader from './components/LogUploader';
import LogViewer from './components/LogViewer';
import RealTimeDashboard from './components/RealTimeDashboard';
import CompetitionDashboard from './components/CompetitionDashboard';
import './App.css';

const { Header, Content, Sider } = Layout;
const { Title } = Typography;

class App extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      selectedKey: 'upload',
      logs: []
    };
  }

  handleMenuClick = ({ key }) => {
    this.setState({ selectedKey: key });
  };

  handleLogsUpdate = (newLogs) => {
    this.setState(prevState => ({
      logs: [...prevState.logs, ...newLogs]
    }));
  };

  renderContent() {
    const { selectedKey, logs } = this.state;

    switch (selectedKey) {
      case 'upload':
        return <LogUploader onLogsUpdate={this.handleLogsUpdate} />;
      case 'viewer':
        return <LogViewer logs={logs} />;
      case 'dashboard':
        return <RealTimeDashboard />;
      case 'competition':
        return <CompetitionDashboard />;
      default:
        return <LogUploader onLogsUpdate={this.handleLogsUpdate} />;
    }
  }

  render() {
    return (
      <Layout style={{ minHeight: '100vh' }}>
        <Sider collapsible>
          <div className="logo">
            <Title level={3} style={{ color: 'white', textAlign: 'center', padding: '16px' }}>
              🚀 TF LogViewer
            </Title>
          </div>
          <Menu
            theme="dark"
            defaultSelectedKeys={['upload']}
            selectedKeys={[this.state.selectedKey]}
            onClick={this.handleMenuClick}
          >
            <Menu.Item key="upload" icon={<UploadOutlined />}>
              Upload Logs
            </Menu.Item>
            <Menu.Item key="viewer" icon={<BarChartOutlined />}>
              Log Viewer
            </Menu.Item>
            <Menu.Item key="dashboard" icon={<DashboardOutlined />}>
              Real-time Dashboard
            </Menu.Item>
            <Menu.Item key="competition" icon={<TrophyOutlined />}>
              Competition Mode
            </Menu.Item>
          </Menu>
        </Sider>
        <Layout>
          <Header style={{ background: '#fff', padding: '0 24px' }}>
            <Title level={2} style={{ margin: 0 }}>
              Terraform LogViewer Pro
            </Title>
          </Header>
          <Content style={{ margin: '24px 16px', padding: 24, background: '#fff' }}>
            {this.renderContent()}
          </Content>
        </Layout>
      </Layout>
    );
  }
}

export default App;