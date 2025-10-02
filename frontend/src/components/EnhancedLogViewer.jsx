// frontend/src/components/EnhancedLogViewerWithFilters.jsx
import React, { useState, useEffect } from 'react';
import { 
  Card, Select, Input, Tag, List, Alert, Collapse, Button, Checkbox, 
  Row, Col, message, Space, Form, Grid, Badge, Tooltip, Divider 
} from 'antd';
import { 
  CaretRightOutlined, CaretDownOutlined, CheckOutlined, EyeOutlined, 
  CodeOutlined, PlusOutlined, DeleteOutlined, SearchOutlined,
  AppstoreOutlined, UnorderedListOutlined, FileTextOutlined 
} from '@ant-design/icons';

const { Option } = Select;
const { Search } = Input;
const { useBreakpoint } = Grid;

const EnhancedLogViewerWithFilters = () => {
  const [entries, setEntries] = useState([]);
  const [allEntries, setAllEntries] = useState([]); // Все записи для фильтрации
  const [totalCount, setTotalCount] = useState(0);
  const [groupedEntries, setGroupedEntries] = useState({});
  const [expandedGroups, setExpandedGroups] = useState(new Set());
  const [expandedLogs, setExpandedLogs] = useState(new Set());
  const [filters, setFilters] = useState({
    operation: '',
    level: '',
    resourceType: '',
    search: '',
    showRead: true
  });
  const [statistics, setStatistics] = useState({});
  const [availableFields, setAvailableFields] = useState([]);
  const [dynamicFilters, setDynamicFilters] = useState([]);
  const [viewMode, setViewMode] = useState('normal');
  const [loading, setLoading] = useState(false);
  const screens = useBreakpoint();

  // Загрузка всех логов без ограничений
  const loadLogs = async () => {
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/v2/entries`);
      const data = await response.json();
      setAllEntries(data); // Сохраняем все записи
      setEntries(data); // И отображаемые записи
      setTotalCount(data.length);
      groupEntries(data);
    } catch (error) {
      console.error('Failed to load logs:', error);
      message.error('Failed to load logs');
    } finally {
      setLoading(false);
    }
  };

  // Применение всех фильтров
  const applyAllFilters = () => {
    let filtered = [...allEntries];

    // Базовые фильтры
    if (filters.operation && filters.operation !== 'all') {
      filtered = filtered.filter(entry => entry.operation === filters.operation);
    }
    if (filters.level && filters.level !== 'all') {
      filtered = filtered.filter(entry => entry.level === filters.level);
    }
    if (filters.search) {
      filtered = filtered.filter(entry => 
        entry.message.toLowerCase().includes(filters.search.toLowerCase()) ||
        (entry.tf_rpc && entry.tf_rpc.toLowerCase().includes(filters.search.toLowerCase()))
      );
    }
    if (!filters.showRead) {
      filtered = filtered.filter(entry => !entry.read);
    }

    // Динамические фильтры
    if (dynamicFilters.length > 0) {
      filtered = filtered.filter(entry => {
        return dynamicFilters.every(df => {
          if (!df.field || !df.value) return true;
          
          // Ищем поле в entry или raw_data
          const fieldValue = entry[df.field] || 
                           (entry.raw_data && entry.raw_data[df.field]) || 
                           '';
          
          return String(fieldValue).toLowerCase().includes(df.value.toLowerCase());
        });
      });
    }

    setEntries(filtered);
    setTotalCount(filtered.length);
    groupEntries(filtered);
  };

  // Загрузка общей статистики
  const loadStatistics = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/v2/statistics');
      const stats = await response.json();
      setStatistics(stats);
    } catch (error) {
      console.error('Failed to load statistics:', error);
    }
  };

  // Загрузка доступных полей
  const loadAvailableFields = async () => {
    try {
      const response = await fetch('http://localhost:8000/api/v2/filter_enh/keys');
      const fields = await response.json();
      setAvailableFields(fields);
    } catch (error) {
      console.error('Failed to load fields:', error);
    }
  };

  // При изменении фильтров применяем все фильтры
  useEffect(() => {
    applyAllFilters();
  }, [filters, dynamicFilters, allEntries]);

  // Первоначальная загрузка
  useEffect(() => {
    loadLogs();
    loadStatistics();
    loadAvailableFields();
  }, []);

  // Группировка записей по tf_req_id для связки запрос-ответ
  const groupEntries = (entries) => {
    const grouped = entries.reduce((acc, entry) => {
      const groupId = entry.tf_req_id || entry.tf_http_trans_id || 'ungrouped';
      if (!acc[groupId]) acc[groupId] = [];
      acc[groupId].push(entry);
      return acc;
    }, {});
    setGroupedEntries(grouped);
  };

  // Добавление динамического фильтра
  const addDynamicFilter = () => {
    setDynamicFilters([...dynamicFilters, { field: '', value: '' }]);
  };

  // Удаление динамического фильтра
  const removeDynamicFilter = (index) => {
    const newFilters = [...dynamicFilters];
    newFilters.splice(index, 1);
    setDynamicFilters(newFilters);
  };

  // Обновление динамического фильтра
  const updateDynamicFilter = (index, field, value) => {
    const newFilters = [...dynamicFilters];
    newFilters[index][field] = value;
    setDynamicFilters(newFilters);
  };

  // Функция сброса фильтров
  const resetFilters = async () => {
    setDynamicFilters([]);
    setFilters({
      operation: '',
      level: '',
      resourceType: '',
      search: '',
      showRead: true
    });
  };

  // Разворот лога
  const toggleLogExpansion = (logId) => {
    setExpandedLogs(prev => {
      const newSet = new Set(prev);
      if (newSet.has(logId)) {
        newSet.delete(logId);
      } else {
        newSet.add(logId);
      }
      return newSet;
    });
  };

  // Разворот группы
  const toggleGroup = (groupId) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupId)) {
        newSet.delete(groupId);
      } else {
        newSet.add(groupId);
      }
      return newSet;
    });
  };

  const getLevelColor = (level) => {
    const colors = {
      error: 'red',
      warn: 'orange',
      info: 'blue',
      debug: 'gray',
      trace: 'lightgray'
    };
    return colors[level] || 'black';
  };

  const getOperationColor = (operation) => {
    const colors = {
      plan: 'blue',
      apply: 'green',
      validate: 'orange',
      unknown: 'gray'
    };
    return colors[operation] || 'gray';
  };

  // Рендер компактного вида
  const renderCompactView = (entries) => {
    return (
      <Row gutter={[16, 16]}>
        {entries.map(entry => (
          <Col xs={24} sm={12} key={entry.id}>
            <Card 
              size="small" 
              className={`log-entry level-${entry.level}`}
              onClick={() => toggleLogExpansion(entry.id)}
              style={{ cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
                    <Tag color={getLevelColor(entry.level)} style={{ margin: 0 }}>
                      {entry.level}
                    </Tag>
                    <span style={{ fontSize: '12px', color: '#666' }}>
                      {new Date(entry.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <div style={{ 
                    fontSize: '12px', 
                    lineHeight: '1.4',
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden'
                  }}>
                    {entry.message}
                  </div>
                </div>
                {entry.tf_req_id && (
                  <Badge count={entry.tf_req_id ? 'Linked' : 0} size="small" />
                )}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    );
  };

  // Рендер обычного вида - компактный как в лог-файле
  const renderNormalView = (entries) => {
    return (
      <div style={{ fontFamily: 'monospace', fontSize: '12px', lineHeight: '1.3' }}>
        {entries.map(entry => (
          <div 
            key={entry.id}
            className={`log-entry level-${entry.level}`}
            style={{ 
              marginBottom: '4px',
              padding: '8px',
              borderRadius: '4px',
              cursor: 'pointer',
              borderLeft: `3px solid ${
                entry.level === 'error' ? '#ff4d4f' :
                entry.level === 'warn' ? '#faad14' :
                entry.level === 'info' ? '#1890ff' :
                entry.level === 'debug' ? '#722ed1' : '#52c41a'
              }`
            }}
            onClick={() => toggleLogExpansion(entry.id)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span style={{ color: '#666' }}>
                {new Date(entry.timestamp).toLocaleString()}
              </span>
              <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                <Tag 
                  color={getLevelColor(entry.level)} 
                  style={{ 
                    margin: 0, 
                    fontSize: '10px', 
                    padding: '0 4px',
                    height: '16px',
                    lineHeight: '16px'
                  }}
                >
                  {entry.level}
                </Tag>
                <Tag 
                  color={getOperationColor(entry.operation)}
                  style={{ 
                    margin: 0, 
                    fontSize: '10px', 
                    padding: '0 4px',
                    height: '16px',
                    lineHeight: '16px'
                  }}
                >
                  {entry.operation}
                </Tag>
                <Button 
                  type="text" 
                  size="small"
                  icon={expandedLogs.has(entry.id) ? <CaretDownOutlined /> : <CaretRightOutlined />}
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleLogExpansion(entry.id);
                  }}
                  style={{ 
                    width: '16px', 
                    height: '16px',
                    fontSize: '10px'
                  }}
                />
              </div>
            </div>
            
            <div style={{ marginBottom: '4px' }}>
              {entry.message}
            </div>

            {entry.tf_resource_type && (
              <Tag 
                style={{ 
                  margin: 0, 
                  fontSize: '10px', 
                  padding: '0 4px',
                  height: '16px',
                  lineHeight: '16px',
                  marginRight: '4px'
                }}
              >
                {entry.tf_resource_type}
              </Tag>
            )}
            {entry.tf_rpc && (
              <Tag 
                color="purple"
                style={{ 
                  margin: 0, 
                  fontSize: '10px', 
                  padding: '0 4px',
                  height: '16px',
                  lineHeight: '16px'
                }}
              >
                {entry.tf_rpc}
              </Tag>
            )}

            {expandedLogs.has(entry.id) && renderLogDetails(entry, 'normal')}
          </div>
        ))}
      </div>
    );
  };

  // Рендер детального вида
  const renderDetailedView = (entries) => {
    return (
      <div>
        {entries.map(entry => (
          <Card 
            key={entry.id} 
            style={{ marginBottom: 8 }}
            title={
              <Space>
                <Tag color={getLevelColor(entry.level)}>{entry.level}</Tag>
                <span>{new Date(entry.timestamp).toLocaleString()}</span>
                <Tag color={getOperationColor(entry.operation)}>
                  {entry.operation}
                </Tag>
              </Space>
            }
            extra={
              <Button 
                type="text" 
                icon={expandedLogs.has(entry.id) ? <CaretDownOutlined /> : <CaretRightOutlined />}
                onClick={() => toggleLogExpansion(entry.id)}
              />
            }
          >
            <div style={{ marginBottom: 16, fontFamily: 'monospace' }}>
              {entry.message}
            </div>
            {expandedLogs.has(entry.id) && renderLogDetails(entry, 'detailed')}
          </Card>
        ))}
      </div>
    );
  };

  // Рендер деталей лога с использованием items вместо children
  const renderLogDetails = (entry, mode) => {
    const items = [
      {
        key: 'basic',
        label: 'Basic Information',
        children: (
          <Row gutter={16}>
            <Col span={12}>
              <strong>Module:</strong> {entry.module || 'N/A'}
            </Col>
            <Col span={12}>
              <strong>Request ID:</strong> {entry.tf_req_id || 'N/A'}
            </Col>
            <Col span={12}>
              <strong>RPC:</strong> {entry.tf_rpc || 'N/A'}
            </Col>
            <Col span={12}>
              <strong>Resource Type:</strong> {entry.tf_resource_type || 'N/A'}
            </Col>
          </Row>
        ),
      }
    ];

    if (entry.description) {
      items.push({
        key: 'description',
        label: 'Description',
        children: <div style={{ whiteSpace: 'pre-wrap' }}>{entry.description}</div>,
      });
    }

    // В normal mode не показываем All Fields
    if (mode === 'detailed') {
      items.push({
        key: 'allFields',
        label: 'All Fields',
        children: (
          <Row gutter={[16, 8]}>
            {Object.entries(entry.raw_data || {}).map(([key, value]) => (
              <Col xs={24} sm={12} md={8} key={key}>
                <div>
                  <strong>{key}:</strong>{' '}
                  <span style={{ wordBreak: 'break-word' }}>
                    {typeof value === 'string' ? value : JSON.stringify(value)}
                  </span>
                </div>
              </Col>
            ))}
          </Row>
        ),
      });
    }

    return (
      <div style={{ 
        marginTop: mode === 'normal' ? 8 : 16, 
        borderTop: '1px solid #f0f0f0', 
        paddingTop: mode === 'normal' ? 8 : 16 
      }}>
        <Collapse 
          defaultActiveKey={['basic']} 
          items={items}
          size={mode === 'normal' ? 'small' : 'default'}
        />
      </div>
    );
  };

  return (
    <div className="log-viewer">
      <Card 
        title={
          <Space>
            <span>Enhanced Terraform Log Viewer</span>
            <Tag color="blue">Total: {totalCount}</Tag>
            {(filters.search || dynamicFilters.length > 0) && (
              <Tag color="orange">Filtered</Tag>
            )}
          </Space>
        } 
        extra={
          <Space>
            <Tooltip title="Compact View">
              <Button 
                type={viewMode === 'compact' ? 'primary' : 'default'}
                icon={<AppstoreOutlined />}
                onClick={() => setViewMode('compact')}
              />
            </Tooltip>
            <Tooltip title="Normal View">
              <Button 
                type={viewMode === 'normal' ? 'primary' : 'default'}
                icon={<UnorderedListOutlined />}
                onClick={() => setViewMode('normal')}
              />
            </Tooltip>
            <Tooltip title="Detailed View">
              <Button 
                type={viewMode === 'detailed' ? 'primary' : 'default'}
                icon={<FileTextOutlined />}
                onClick={() => setViewMode('detailed')}
              />
            </Tooltip>
            <Button onClick={loadLogs} loading={loading}>
              Refresh
            </Button>
          </Space>
        }
      >
        {/* Основные фильтры */}
        <Card size="small" title="Basic Filters" style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col xs={24} sm={6}>
              <Select 
                value={filters.operation} 
                onChange={value => setFilters({...filters, operation: value})}
                placeholder="Operation"
                style={{ width: '100%' }}
                allowClear
              >
                <Option value="plan">Plan</Option>
                <Option value="apply">Apply</Option>
                <Option value="validate">Validate</Option>
                <Option value="unknown">Unknown</Option>
              </Select>
            </Col>
            <Col xs={24} sm={6}>
              <Select 
                value={filters.level}
                onChange={value => setFilters({...filters, level: value})}
                placeholder="Log Level"
                style={{ width: '100%' }}
                allowClear
              >
                <Option value="error">Error</Option>
                <Option value="warn">Warning</Option>
                <Option value="info">Info</Option>
                <Option value="debug">Debug</Option>
                <Option value="trace">Trace</Option>
              </Select>
            </Col>
            <Col xs={24} sm={8}>
              <Search
                placeholder="Search messages, resources, RPC..."
                value={filters.search}
                onChange={e => setFilters({...filters, search: e.target.value})}
                style={{ width: '100%' }}
              />
            </Col>
            {/* <Col xs={24} sm={4}>
              <Checkbox
                checked={filters.showRead}
                onChange={e => setFilters({...filters, showRead: e.target.checked})}
              >
                Show Read
              </Checkbox>
            </Col> */}
          </Row>
        </Card>

        {/* Динамические фильтры */}
        <Card size="small" title="Dynamic Field Filters" style={{ marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {dynamicFilters.map((filter, index) => (
              <Space key={index} style={{ width: '100%' }}>
                <Select
                  value={filter.field}
                  onChange={value => updateDynamicFilter(index, 'field', value)}
                  placeholder="Select field"
                  style={{ width: 200 }}
                  showSearch
                >
                  {availableFields.map(field => (
                    <Option key={field} value={field}>{field}</Option>
                  ))}
                </Select>
                <Input
                  value={filter.value}
                  onChange={e => updateDynamicFilter(index, 'value', e.target.value)}
                  placeholder="Filter value"
                  style={{ width: 200 }}
                />
                <Button 
                  danger 
                  icon={<DeleteOutlined />}
                  onClick={() => removeDynamicFilter(index)}
                />
              </Space>
            ))}
            
            <Space>
              <Button 
                type="dashed" 
                icon={<PlusOutlined />}
                onClick={addDynamicFilter}
              >
                Add Filter
              </Button>
              <Button 
                icon={<DeleteOutlined />}
                onClick={resetFilters}
                disabled={!filters.search && dynamicFilters.length === 0}
              >
                Reset All Filters
              </Button>
            </Space>
          </Space>
        </Card>

        {/* Группировка по запросам-ответам */}
        <div className="log-groups">
          {Object.entries(groupedEntries).map(([groupId, groupEntries]) => (
            <Card 
              key={groupId} 
              size="small" 
              title={
                <div 
                  style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}
                  onClick={() => toggleGroup(groupId)}
                >
                  {expandedGroups.has(groupId) ? <CaretDownOutlined /> : <CaretRightOutlined />}
                  <span>
                    {groupId === 'ungrouped' ? 'Ungrouped Entries' : `Request Group: ${groupId}`}
                  </span>
                  <Tag color="blue">{groupEntries.length} entries</Tag>
                  {groupId !== 'ungrouped' && (
                    <Tag color={getOperationColor(groupEntries[0]?.operation)}>
                      {groupEntries[0]?.operation}
                    </Tag>
                  )}
                </div>
              }
              style={{ marginBottom: 16 }}
            >
              {expandedGroups.has(groupId) && (
                <>
                  {viewMode === 'compact' && renderCompactView(groupEntries)}
                  {viewMode === 'normal' && renderNormalView(groupEntries)}
                  {viewMode === 'detailed' && renderDetailedView(groupEntries)}
                </>
              )}
            </Card>
          ))}
        </div>

        {entries.length === 0 && !loading && (
          <Alert 
            message="No logs found" 
            description="Upload some Terraform logs first or adjust your filters"
            type="info"
            showIcon
          />
        )}

        {loading && (
          <Alert 
            message="Loading all logs..." 
            description="Please wait while we load all log entries"
            type="info"
            showIcon
          />
        )}
      </Card>
    </div>
  );
};

export default EnhancedLogViewerWithFilters;