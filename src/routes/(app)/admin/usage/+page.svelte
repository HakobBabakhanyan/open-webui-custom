<script lang="ts">
	import { onMount, getContext } from 'svelte';
	import { user } from '$lib/stores';
	import { getAdminUsageSummary, type AdminUsageModel, type AdminUsageSummary } from '$lib/apis';
	import { goto } from '$app/navigation';

	const i18n = getContext('i18n');

	let loading = true;
	let failed = false;
	let query = '';
	let sortKey: 'total_tokens' | 'cost_micros' | 'request_count' | 'updated_at' = 'total_tokens';
	let summary: AdminUsageSummary | null = null;
	let openUserId: string | null = null;

	const formatTokens = (value: number) => new Intl.NumberFormat().format(value || 0);

	const formatMoney = (micros: number) => {
		const usd = (micros || 0) / 1_000_000;
		const digits = usd > 0 && usd < 0.01 ? 4 : 2;
		return usd.toLocaleString(undefined, {
			style: 'currency',
			currency: 'USD',
			minimumFractionDigits: digits,
			maximumFractionDigits: digits
		});
	};

	const formatUpdated = (timestamp: number) =>
		timestamp ? new Date(timestamp * 1000).toLocaleString() : '—';

	$: users = (summary?.users ?? []).filter((row) => {
		const needle = query.trim().toLowerCase();
		if (!needle) return true;
		return [row.user_name, row.user_email, row.user_id].some((value) =>
			(value || '').toLowerCase().includes(needle)
		);
	});

	$: sortedUsers = [...users].sort((a, b) => (b[sortKey] || 0) - (a[sortKey] || 0));
	$: totalTokens = summary?.totals.total_tokens || 0;

	const share = (tokens: number) => (totalTokens > 0 ? Math.round((tokens / totalTokens) * 100) : 0);

	const modelsFor = (userId: string) =>
		(summary?.models ?? [])
			.filter((row) => row.user_id === userId)
			.sort((a, b) => b.total_tokens - a.total_tokens);

	const topModels = (rows: AdminUsageModel[]) => {
		const grouped = new Map<string, AdminUsageModel>();
		for (const row of rows) {
			const current = grouped.get(row.model);
			if (!current) {
				grouped.set(row.model, { ...row, user_id: '' });
				continue;
			}
			current.request_count += row.request_count;
			current.prompt_tokens += row.prompt_tokens;
			current.completion_tokens += row.completion_tokens;
			current.total_tokens += row.total_tokens;
			current.cost_micros += row.cost_micros;
			current.unpriced_tokens += row.unpriced_tokens;
		}
		return [...grouped.values()].sort((a, b) => b.total_tokens - a.total_tokens);
	};

	$: modelRows = topModels(summary?.models ?? []);

	const loadData = async () => {
		loading = true;
		failed = false;
		try {
			summary = await getAdminUsageSummary(localStorage.token ?? '');
		} catch (error) {
			console.error(error);
			failed = true;
			summary = null;
		} finally {
			loading = false;
		}
	};

	onMount(async () => {
		if ($user?.role !== 'admin') {
			await goto('/');
			return;
		}
		await loadData();
	});

	const cards = (data: AdminUsageSummary | null) => [
		{ label: 'Users', value: formatTokens(data?.totals.users ?? 0) },
		{ label: 'Requests', value: formatTokens(data?.totals.request_count ?? 0) },
		{ label: 'Input tokens', value: formatTokens(data?.totals.prompt_tokens ?? 0) },
		{ label: 'Output tokens', value: formatTokens(data?.totals.completion_tokens ?? 0) },
		{ label: 'Total tokens', value: formatTokens(data?.totals.total_tokens ?? 0) },
		{ label: 'Estimated spend', value: formatMoney(data?.totals.cost_micros ?? 0) }
	];
</script>

<div class="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-5 md:px-6">
	<div class="flex flex-col gap-1">
		<h2 class="text-xl font-medium">{$i18n.t('Usage')}</h2>
		<p class="text-sm text-gray-500">
			{$i18n.t('Lifetime totals. Open a user to see which model the tokens came from.')}
		</p>
	</div>

	{#if loading}
		<div class="text-sm text-gray-500">{$i18n.t('Loading...')}</div>
	{:else if failed}
		<div class="text-sm text-red-500">{$i18n.t('Failed to load usage.')}</div>
	{:else}
		<div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
			{#each cards(summary) as card}
				<div class="rounded-xl border border-gray-100 px-3 py-3 dark:border-gray-850">
					<div class="text-xs text-gray-500">{card.label}</div>
					<div class="mt-1 text-lg font-medium">{card.value}</div>
				</div>
			{/each}
		</div>

		{#if (summary?.totals.unpriced_tokens ?? 0) > 0}
			<div class="text-xs text-gray-500">
				{formatTokens(summary?.totals.unpriced_tokens ?? 0)}
				{$i18n.t('tokens are counted, but their model has no price, so they are not included in spend.')}
			</div>
		{/if}

		<input
			class="w-full rounded-xl border border-gray-100 bg-transparent px-3 py-2 text-sm outline-none dark:border-gray-850"
			bind:value={query}
			placeholder={$i18n.t('Search by name or email')}
		/>

		<div class="flex flex-col gap-2">
			<h3 class="text-sm font-medium">{$i18n.t('Where tokens are spent')}</h3>
			<div class="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-850">
				<table class="min-w-full text-sm">
					<thead class="bg-gray-50 text-xs text-gray-500 dark:bg-gray-900">
						<tr>
							<th class="px-3 py-2 text-left font-medium">{$i18n.t('Model')}</th>
							<th class="px-3 py-2 text-right font-medium">{$i18n.t('Requests')}</th>
							<th class="px-3 py-2 text-right font-medium">{$i18n.t('Input')}</th>
							<th class="px-3 py-2 text-right font-medium">{$i18n.t('Output')}</th>
							<th class="px-3 py-2 text-right font-medium">{$i18n.t('Total tokens')}</th>
							<th class="px-3 py-2 text-right font-medium">{$i18n.t('Share')}</th>
							<th class="px-3 py-2 text-right font-medium">{$i18n.t('Estimated spend')}</th>
						</tr>
					</thead>
					<tbody>
						{#if modelRows.length === 0}
							<tr>
								<td colspan="7" class="px-3 py-6 text-center text-gray-400">
									{$i18n.t('Model totals start with the next request. Older totals have no model split.')}
								</td>
							</tr>
						{:else}
							{#each modelRows as row (row.model)}
								<tr class="border-t border-gray-100 dark:border-gray-850">
									<td class="px-3 py-2 font-mono text-xs">{row.model}</td>
									<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.request_count)}</td>
									<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.prompt_tokens)}</td>
									<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.completion_tokens)}</td>
									<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.total_tokens)}</td>
									<td class="px-3 py-2 text-right tabular-nums">{share(row.total_tokens)}%</td>
									<td class="px-3 py-2 text-right tabular-nums">{formatMoney(row.cost_micros)}</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>
		</div>

		<div class="overflow-x-auto rounded-xl border border-gray-100 dark:border-gray-850">
			<table class="min-w-full text-sm">
				<thead class="bg-gray-50 text-xs text-gray-500 dark:bg-gray-900">
					<tr>
						<th class="px-3 py-2 text-left font-medium">{$i18n.t('User')}</th>
						<th class="px-3 py-2 text-right font-medium">
							<button class="hover:text-gray-900 dark:hover:text-white" on:click={() => (sortKey = 'request_count')}>
								{$i18n.t('Requests')}
							</button>
						</th>
						<th class="px-3 py-2 text-right font-medium">{$i18n.t('Input')}</th>
						<th class="px-3 py-2 text-right font-medium">{$i18n.t('Output')}</th>
						<th class="px-3 py-2 text-right font-medium">
							<button class="hover:text-gray-900 dark:hover:text-white" on:click={() => (sortKey = 'total_tokens')}>
								{$i18n.t('Total tokens')}
							</button>
						</th>
						<th class="px-3 py-2 text-right font-medium">{$i18n.t('Share')}</th>
						<th class="px-3 py-2 text-right font-medium">
							<button class="hover:text-gray-900 dark:hover:text-white" on:click={() => (sortKey = 'cost_micros')}>
								{$i18n.t('Estimated spend')}
							</button>
						</th>
						<th class="px-3 py-2 text-right font-medium">
							<button class="hover:text-gray-900 dark:hover:text-white" on:click={() => (sortKey = 'updated_at')}>
								{$i18n.t('Updated')}
							</button>
						</th>
					</tr>
				</thead>
				<tbody>
					{#if sortedUsers.length === 0}
						<tr>
							<td colspan="8" class="px-3 py-8 text-center text-gray-400">
								{$i18n.t('No usage yet')}
							</td>
						</tr>
					{:else}
						{#each sortedUsers as row (row.user_id)}
							<tr
								class="cursor-pointer border-t border-gray-100 dark:border-gray-850"
								on:click={() => (openUserId = openUserId === row.user_id ? null : row.user_id)}
							>
								<td class="px-3 py-2">
									<div>{row.user_name || row.user_email || row.user_id}</div>
									{#if row.user_email && row.user_name}
										<div class="text-xs text-gray-500">{row.user_email}</div>
									{/if}
								</td>
								<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.request_count)}</td>
								<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.prompt_tokens)}</td>
								<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.completion_tokens)}</td>
								<td class="px-3 py-2 text-right tabular-nums">{formatTokens(row.total_tokens)}</td>
								<td class="px-3 py-2 text-right tabular-nums">{share(row.total_tokens)}%</td>
								<td class="px-3 py-2 text-right tabular-nums">
									{formatMoney(row.cost_micros)}
									{#if row.unpriced_tokens > 0}
										<div class="text-[11px] text-gray-400">
											{formatTokens(row.unpriced_tokens)} {$i18n.t('unpriced')}
										</div>
									{/if}
								</td>
								<td class="px-3 py-2 text-right text-xs text-gray-500">{formatUpdated(row.updated_at)}</td>
							</tr>
							{#if openUserId === row.user_id}
								<tr class="border-t border-gray-100 bg-gray-50 dark:border-gray-850 dark:bg-gray-900">
									<td colspan="8" class="px-3 py-3">
										{#if modelsFor(row.user_id).length === 0}
											<div class="text-xs text-gray-500">
												{$i18n.t('No model split yet. It appears after this user sends another request.')}
											</div>
										{:else}
											<div class="flex flex-col gap-1 text-xs">
												{#each modelsFor(row.user_id) as model}
													<div class="flex items-center justify-between gap-3">
														<span class="font-mono">{model.model}</span>
														<span class="tabular-nums text-gray-500">
															{formatTokens(model.prompt_tokens)} {$i18n.t('in')} /
															{formatTokens(model.completion_tokens)} {$i18n.t('out')} /
															{formatTokens(model.total_tokens)} /
															{formatMoney(model.cost_micros)}
														</span>
													</div>
												{/each}
											</div>
										{/if}
									</td>
								</tr>
							{/if}
						{/each}
					{/if}
				</tbody>
			</table>
		</div>
	{/if}
</div>
