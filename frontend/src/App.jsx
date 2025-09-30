import React from 'react';
import { Layout, Menu, Typography } from 'antd';
import {
  UploadOutlined,
  DashboardOutlined,
  BarChartOutlined,
  TrophyOutlined,
  LineChartOutlined,
  ExportOutlined
} from '@ant-design/icons';
import LogUploader from './components/LogUploader';
import EnhancedLogViewer from './components/EnhancedLogViewer';
import LogViewer from './components/LogViewer';
import RealTimeDashboard from './components/RealTimeDashboard';
import CompetitionDashboard from './components/CompetitionDashboard';
import GanttChart from './components/GanttChart';
import ExportPanel from './components/ExportPanel';
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

  // Обновленный items для Menu
  menuItems = [
    {
      key: 'upload',
      icon: <UploadOutlined />,
      label: 'Upload Logs',
    },
    {
        key: 'old_viewer',
        icon: <BarChartOutlined />,
        label: 'Old Log Viewer',
    },
    {
      key: 'viewer',
      icon: <BarChartOutlined />,
      label: 'Enhanced Log Viewer',
    },
    {
      key: 'gantt',
      icon: <LineChartOutlined />,
      label: 'Gantt Chart',
    },
    {
      key: 'dashboard',
      icon: <DashboardOutlined />,
      label: 'Real-time Dashboard',
    },
    {
      key: 'competition',
      icon: <TrophyOutlined />,
      label: 'Competition Mode',
    },
    {
      key: 'export',
      icon: <ExportOutlined />,
      label: 'Export Data',
    },
  ];

  renderContent() {
    const { selectedKey, logs } = this.state;

    switch (selectedKey) {
      case 'upload':
        return <LogUploader onLogsUpdate={this.handleLogsUpdate} />;
     case 'old_viewer':
        return <LogViewer logs={logs} />;
      case 'viewer':
        return <EnhancedLogViewer logs={logs} />;
      case 'gantt':
        return <GanttChart />;
      case 'dashboard':
        return <RealTimeDashboard />;
      case 'competition':
        return <CompetitionDashboard />;
      case 'export':
        return <ExportPanel />;
      default:
        return <LogUploader onLogsUpdate={this.handleLogsUpdate} />;
    }
  }

  render() {
    return (
      <Layout style={{ minHeight: '100vh' }}>
        <Sider collapsible>
          <div className="logo">
            <Title level={5} style={{ color: 'white', textAlign: 'center', padding: '3px' }}>
              🚀 TF LogViewer
            </Title>
          </div>
          <Menu
            theme="dark"
            defaultSelectedKeys={['upload']}
            selectedKeys={[this.state.selectedKey]}
            onClick={this.handleMenuClick}
            items={this.menuItems}  // Используем items вместо children
          />
        </Sider>
        <Layout>
          <Header style={{ background: '#fff', padding: '0 24px' }}>
            <Title level={2} style={{ margin: 0 }}>
              Terraform LogViewer Pro - Competition Edition
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