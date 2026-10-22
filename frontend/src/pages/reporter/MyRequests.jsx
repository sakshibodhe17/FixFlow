import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PlusCircle } from 'lucide-react';
import RequestTable from '../../components/RequestTable';
import { Button, Empty, ErrorNote, PageHeader, Panel, Spinner, Tabs } from '../../components/ui';
import { useApi } from '../../lib/hooks';

export default function MyRequests() {
  const [tab, setTab] = useState('active');
  const { data, loading, error } = useApi('/requests', { params: { mine: true, limit: 200 }, pollMs: 15000 });
  const items = data?.items || [];
  const groups = {
    active: items.filter((r) => !['Resolved', 'Closed'].includes(r.status)),
    review: items.filter((r) => r.status === 'Resolved'),
    all: items,
  };

  return (
    <>
      <PageHeader title="My requests" subtitle="Statuses update automatically while this page is open."
        actions={<Link to="/report"><Button icon={PlusCircle}>Report a problem</Button></Link>} />
      {groups.review.length > 0 && (
        <div className="mb-4 rounded border border-moss/30 bg-moss-light px-4 py-3 text-sm text-moss">
          {groups.review.length === 1 ? '1 repair is' : `${groups.review.length} repairs are`} marked fixed. Confirm and rate, or reopen if the problem is still there.
        </div>
      )}
      <Panel>
        <Tabs value={tab} onChange={setTab} tabs={[
          { value: 'active', label: 'In progress', count: groups.active.length },
          { value: 'review', label: 'Waiting for your review', count: groups.review.length },
          { value: 'all', label: 'All', count: groups.all.length },
        ]} />
        <ErrorNote>{error}</ErrorNote>
        {loading ? <Spinner /> : (
          <RequestTable items={groups[tab]} empty={
            <Empty title={tab === 'all' ? "You haven't reported anything yet." : 'Nothing here right now.'}
              action={tab === 'all' && <Link to="/report"><Button>Report a problem</Button></Link>}>
              {tab === 'all' && 'Spotted something broken? Scan the QR sticker on it or pick its location.'}
            </Empty>} />
        )}
      </Panel>
    </>
  );
}
