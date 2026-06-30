import { useCallback, useState } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { ConnectionPage } from './components/ConnectionPage';
import { Shell } from './components/layout/Shell';
import { DashboardPage } from './components/pages/DashboardPage';
import { DronePage } from './components/pages/DronePage';
import { AIChatFAB } from './components/ai/AIChatFAB';
import { AIChatDialog } from './components/ai/AIChatDialog';
import { useOpenClawChat } from './hooks/useOpenClawChat';
import { FleetProvider } from './context/FleetContext';
import { useFleet } from './context/useFleet';
import type { PageId, RobotType } from './types/FleetTypes';
import './App.css';

const PLATFORM_TABS = [
  { id: 'ground', label: 'Go2 地面' },
  { id: 'drone', label: 'UAV 无人机' },
];

function AppContent() {
  const { robots, activeRobotId, addRobot, removeRobot, selectRobot, reconnectRobot } = useFleet();
  const [activePage, setActivePage] = useState<PageId>('dashboard');
  const [activePlatform, setActivePlatform] = useState('ground');
  const [showConnectionPage, setShowConnectionPage] = useState(false);
  const [showAIChat, setShowAIChat] = useState(false);

  const chat = useOpenClawChat();

  const hasOnlineRobot = robots.some((r) => r.status === 'online');
  const selectedRobotId = activeRobotId || robots.find((r) => r.status === 'online')?.id || null;

  const handleConnect = useCallback(async (url: string, type: RobotType): Promise<boolean> => {
    let ip = 'localhost';
    let port = '9090';
    try {
      const cleaned = url.replace('ws://', '').replace('wss://', '').replace('/','');
      const parts = cleaned.split(':');
      ip = parts[0] || 'localhost';
      port = parts[1] || '9090';
    } catch { /* fallback to defaults */ }
    const name = type === 'uav' ? 'Drone' : type === 'tb4' ? 'TurtleBot4' : 'Go2';
    const robot = await addRobot(name, type, ip, port);
    if (robot.status === 'online') {
      selectRobot(robot.id);
      setShowConnectionPage(false);
      if (type === 'uav') setActivePlatform('drone');
      return true;
    }
    return false;
  }, [addRobot, selectRobot]);

  const handleAddRobot = useCallback(() => setShowConnectionPage(true), []);
  const handleNavigate = useCallback((page: PageId) => setActivePage(page), []);
  const handleSelectRobot = useCallback((id: string) => selectRobot(id), [selectRobot]);

  if (!hasOnlineRobot && robots.length === 0 && !showConnectionPage) {
    return (
      <>
        <ConnectionPage onConnect={handleConnect} />
        <AIChatFAB
          connected
          hasNewMessage={false}
          onClick={() => setShowAIChat(true)}
        />
        {showAIChat && (
          <AIChatDialog
            conversations={chat.conversations}
            activeConversationId={chat.activeConversationId}
            messages={chat.activeMessages}
            isStreaming={chat.isStreaming}
            settings={chat.settings}
            onSend={chat.sendMessage}
            onStop={chat.stopStreaming}
            onRetry={chat.retryLast}
            onRegenerate={chat.regenerate}
            onCreateConversation={chat.createConversation}
            onDeleteConversation={chat.deleteConversation}
            onSwitchConversation={chat.switchConversation}
            onUpdateSettings={chat.updateSettings}
            onClose={() => setShowAIChat(false)}
            connected
          />
        )}
        <ToastContainer />
      </>
    );
  }

  return (
    <>
      {showConnectionPage ? (
        <ConnectionPage onConnect={handleConnect} onCancel={() => setShowConnectionPage(false)} />
      ) : (
        <Shell
          activePage={activePage}
          pageTitle="RobotCore"
          tabs={PLATFORM_TABS}
          activeTab={activePlatform}
          onTabChange={setActivePlatform}
          onNavigate={handleNavigate}
          onSelectRobot={handleSelectRobot}
        >
          {activePlatform === 'ground' && activePage === 'dashboard' && (
            <DashboardPage
              robots={robots}
              selectedRobotId={selectedRobotId}
              onSelectRobot={handleSelectRobot}
              onReconnectRobot={reconnectRobot}
              onAddRobot={handleAddRobot}
              onRemoveRobot={removeRobot}
            />
          )}
          {activePlatform === 'drone' && (
            <DronePage robots={robots} />
          )}
          {activePlatform === 'ground' && activePage !== 'dashboard' && (
            <div className="card" style={{ textAlign: 'center', padding: 48 }}>
              <div className="card-sub" style={{ fontSize: 14 }}>页面建设中</div>
            </div>
          )}
        </Shell>
      )}
      <AIChatFAB
        connected
        hasNewMessage={false}
        onClick={() => setShowAIChat(true)}
      />
      {showAIChat && (
        <AIChatDialog
          conversations={chat.conversations}
          activeConversationId={chat.activeConversationId}
          messages={chat.activeMessages}
          isStreaming={chat.isStreaming}
          settings={chat.settings}
          onSend={chat.sendMessage}
          onStop={chat.stopStreaming}
          onRetry={chat.retryLast}
          onRegenerate={chat.regenerate}
          onCreateConversation={chat.createConversation}
          onDeleteConversation={chat.deleteConversation}
          onSwitchConversation={chat.switchConversation}
          onUpdateSettings={chat.updateSettings}
          onClose={() => setShowAIChat(false)}
          connected
        />
      )}
      <ToastContainer position="top-center" />
    </>
  );
}

export default function App() {
  return (
    <FleetProvider>
      <AppContent />
    </FleetProvider>
  );
}
