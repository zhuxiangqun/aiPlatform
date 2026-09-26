import { assessClassHygiene, bilingual, classDisplay, fieldDisplay, hasCjk, propDisplay } from './ontologyDisplay';

describe('ontologyDisplay bilingual', () => {
  it('shows English（中文） when label is Chinese', () => {
    expect(classDisplay({ uri: '.../InstallOrder', label: '安装工单' })).toBe(
      'InstallOrder（安装工单）',
    );
  });

  it('does not show English（English） for table-alias labels', () => {
    expect(classDisplay({ uri: '.../InstallTicket', label: 'install_tickets' })).toBe(
      'InstallTicket（安装票据）',
    );
    expect(classDisplay({ uri: '.../AlertEvent', label: 'alert_events' })).toBe(
      'AlertEvent（告警事件）',
    );
  });

  it('bilingual requires CJK on the second part', () => {
    expect(bilingual('InstallTicket', 'install_tickets')).toBe('InstallTicket');
    expect(bilingual('assigned_to', '派单给')).toBe('assigned_to（派单给）');
    expect(hasCjk('install_tickets')).toBe(false);
  });

  it('fieldDisplay uses soft Chinese when meta missing', () => {
    expect(fieldDisplay('severity')).toBe('severity（严重级别）');
    expect(fieldDisplay('ticket_id')).toBe('ticket_id（票据号）');
  });

  it('propDisplay skips non-Chinese labels', () => {
    expect(propDisplay({ uri: '.../assigned_to', label: '派单给' })).toBe(
      'assigned_to（派单给）',
    );
    expect(propDisplay({ uri: '.../foo', label: 'foo_bar' })).toBe('foo');
  });
});

describe('assessClassHygiene dirty classes', () => {
  it('flags 类型词 URI + 实例 label', () => {
    const h = assessClassHygiene({
      uri: '.../安装工单',
      label: '智能锁安装服务',
      required_fields: ['name'],
    });
    expect(h.dirty).toBe(true);
  });

  it('flags person-like thin Chinese label', () => {
    const h = assessClassHygiene({
      uri: '.../王五',
      label: '王五',
      required_fields: ['name'],
    });
    expect(h.dirty).toBe(true);
  });

  it('does not flag normal InstallOrder', () => {
    const h = assessClassHygiene({
      uri: '.../InstallOrder',
      label: '安装工单',
      required_fields: ['order_id', 'customer_name', 'device_model', 'status'],
      optional_fields: ['address'],
      states: { enum: [{ name: 'pending' }] },
    });
    expect(h.dirty).toBe(false);
  });

  it('flags snake_case thin table dump', () => {
    const h = assessClassHygiene({
      uri: '.../install_tickets',
      label: 'install_tickets',
      required_fields: ['name'],
    });
    expect(h.dirty).toBe(true);
  });
});
