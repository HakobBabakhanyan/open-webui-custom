<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getAdminUsageSummary, getAdminUsageLogs } from '$lib/apis';
	import { goto } from '$app/navigation';

	const i18n = getContext('i18n');

	let loading = true;
	let summary: Array<{ user_id: string; request_count: number; total_tokens: number }> = [];
	let logs: Array<any> = [];
	let totalLogs = 0;

	let selectedUserId: string | null = null;

	async function loadData() {
		loading = true;
		try {
			const token = localStorage.token ?? '';
			summary = await getAdminUsageSummary(token);
			if (selectedUserId) {
				const row = (summary ?? []).find((r) => r.user_id === selectedUserId);
				const res = await getAdminUsageLogs(token, {
					user_id: selectedUserId,
					user_email: row?.user_email,
					limit: 50
				});
				logs = res?.logs ?? [];
				totalLogs = res?.total ?? 0;
			} else {
				logs = [];
				totalLogs = 0;
			}
		} catch (e) {
			console.error(e);
		} finally {
			loading = false;
		}
	}

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}
		await loadData();
	});
</script>

<div class="p-4 md:p-6">
	<h2 class="text-xl font-semibold mb-3">{$i18n.t('Usage Summary')}</h2>

	{#if loading}
		<div class="text-sm text-gray-500">{$i18n.t('Loading...')}</div>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
			<table class="min-w-full text-sm">
				<thead class="bg-gray-50 dark:bg-gray-900">
					<tr>
						<th class="text-left px-3 py-2">{$i18n.t('User Email')}</th>
						<th class="text-left px-3 py-2">{$i18n.t('Requests')}</th>
						<th class="text-left px-3 py-2">{$i18n.t('Total Tokens')}</th>
						<th class="text-left px-3 py-2"></th>
					</tr>
				</thead>
				<tbody>
					{#if (summary ?? []).length === 0}
						<tr>
							<td colspan="4" class="px-3 py-4 text-gray-400 text-center">
								{$i18n.t('No usage yet')}
							</td>
						</tr>
					{:else}
						{#each summary as row}
							<tr class="border-t border-gray-100 dark:border-gray-800">
								<td class="px-3 py-2">
									{#if row.user_email}
										<span>{row.user_email}</span>
										<div class="text-[11px] text-gray-400 font-mono">{row.user_id}</div>
									{:else}
										<span class="font-mono">{row.user_id}</span>
									{/if}
								</td>
								<td class="px-3 py-2">{row.request_count}</td>
								<td class="px-3 py-2">{row.total_tokens}</td>
								<td class="px-3 py-2">
									<button
										class="text-blue-600 hover:underline"
										on:click={async () => {
											selectedUserId = row.user_id;
											await loadData();
										}}
									>
										{$i18n.t('View Logs')}
									</button>
								</td>
							</tr>
						{/each}
					{/if}
				</tbody>
			</table>
		</div>

		{#if selectedUserId}
			<h3 class="text-lg font-semibold mt-6 mb-2">
				{$i18n.t('Recent Requests for')} <span class="font-mono">{selectedUserId}</span>
			</h3>
			<div class="text-xs text-gray-500 mb-2">{$i18n.t('Showing up to 50 latest entries')}</div>
			<div class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
				<table class="min-w-full text-sm">
					<thead class="bg-gray-50 dark:bg-gray-900">
						<tr>
							<th class="text-left px-3 py-2">{$i18n.t('Timestamp')}</th>
							<th class="text-left px-3 py-2">{$i18n.t('Provider')}</th>
							<th class="text-left px-3 py-2">{$i18n.t('Endpoint')}</th>
							<th class="text-left px-3 py-2">{$i18n.t('Model')}</th>
							<th class="text-left px-3 py-2">{$i18n.t('Prompt Tokens')}</th>
							<th class="text-left px-3 py-2">{$i18n.t('Completion Tokens')}</th>
							<th class="text-left px-3 py-2">{$i18n.t('Total Tokens')}</th>
						</tr>
					</thead>
					<tbody>
						{#if (logs ?? []).length === 0}
							<tr>
								<td colspan="7" class="px-3 py-4 text-gray-400 text-center">
									{$i18n.t('No logs for this user')}
								</td>
							</tr>
						{:else}
							{#each logs as log}
								<tr class="border-t border-gray-100 dark:border-gray-800">
									<td class="px-3 py-2">{new Date((log.created_at ?? 0) * 1000).toLocaleString()}</td>
									<td class="px-3 py-2">{log.provider}</td>
									<td class="px-3 py-2">{log.endpoint}</td>
									<td class="px-3 py-2">{log.model}</td>
									<td class="px-3 py-2">{log.prompt_tokens ?? '-'}</td>
									<td class="px-3 py-2">{log.completion_tokens ?? '-'}</td>
									<td class="px-3 py-2">{log.total_tokens ?? '-'}</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>
		{/if}
	{/if}
</div>


