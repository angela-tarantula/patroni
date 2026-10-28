.. _pause:

Pause/Resume mode for the cluster
=================================

The goal
--------

Under certain circumstances Patroni needs to temporarily step down from managing the cluster, while still retaining the cluster state in DCS. Possible use cases are uncommon activities on the cluster, such as major version upgrades or corruption recovery. During those activities nodes are often started and stopped for reasons unknown to Patroni, some nodes can be even temporarily promoted, violating the assumption of running only one primary. Therefore, Patroni needs to be able to "detach" from the running cluster, implementing an equivalent of the maintenance mode in Pacemaker.



The implementation
------------------

When Patroni runs in a paused mode, it does not change the state of PostgreSQL, except for the following cases:

- For each node, the member key in DCS is updated with the current information about the cluster. This causes Patroni to run read-only queries on a member node if the member is running.

- For the Postgres primary with the leader lock Patroni updates the lock. If the node with the leader lock stops being the primary (i.e. is demoted manually), Patroni will release the lock instead of promoting the node back.

- Manual unscheduled restart, manual unscheduled failover/switchover and reinitialize are allowed. No scheduled action is allowed. Manual switchover is only allowed if the node to switch over to is specified.

- If 'parallel' primaries are detected by Patroni, it emits a warning, but does not demote the primary without the leader lock.

- If there is no leader lock in the cluster, the running primary acquires the lock. If there is more than one primary node, then the first primary to acquire the lock wins. If there are no primary altogether, Patroni does not try to promote any replicas. There is an exception in this rule: if there is no leader lock because the old primary has demoted itself due to the manual promotion, then only the candidate node mentioned in the promotion request may take the leader lock. When the new leader lock is granted (i.e. after promoting a replica manually), Patroni makes sure the replicas that were streaming from the previous leader will switch to the new one.

- When Postgres is stopped, Patroni does not try to start it. When Patroni is stopped, it does not try to stop the Postgres instance it is managing.

- Patroni will not try to remove replication slots that don't represent the other cluster member or are not listed in the configuration of the permanent slots.

User guide
----------

``patronictl`` supports :ref:`pause <patronictl_pause>` and :ref:`resume <patronictl_resume>` commands.

One can also issue a ``PATCH /config`` request to the Patroni :ref:`REST API <config_endpoint>` with ``{"pause": true/false/null}``.

.. _pause_maintenance_key:

The maintenance key
-------------------

Patroni keeps the pause decision in the ``/config`` key in DCS, ``{namespace}/{cluster}/config``, which holds the dynamic configuration. It mirrors the decision in the maintenance key, ``{namespace}/{cluster}/maintenance``, so that a cluster can still be paused or resumed after the DCS has lost its data. On Kubernetes these are the ``config`` and ``maintenance`` annotations of the ``{cluster}-config`` object. The maintenance key contains a JSON object such as ``{"pause": true}``, which may contain other fields.

While ``/config`` exists, it decides the pause state. When it is missing, a ``PATCH /config`` REST API request containing only ``pause`` records the decision in the maintenance key without creating ``/config``. Nodes follow that decision, and Patroni carries it into a rebuilt ``/config``. If neither DCS key holds a decision, each running Patroni keeps its last known pause state. While ``/config`` exists, ``patronictl`` and the REST API keep the maintenance key in step whenever a write changes the resulting pause state.

Tools that write ``pause`` into ``/config`` directly in the DCS keep working: Patroni copies the change into the maintenance key within one HA loop. To minimize the time for which the keys can disagree, use ``patronictl`` or the REST API, or update both keys directly. Tools that write both keys should follow these rules:

- A change is complete once both keys hold the intended value.
- If either write fails, reload both values and reapply the intended change against the new state. Do not replay stale serialized values.
- Change only ``pause`` in the maintenance key, and keep its other fields unchanged.
- On Kubernetes, write both annotations in one patch. They share the object's resource version, so after one patch succeeds, a second patch using the originally read resource version would fail.
