import 'package:flutter/material.dart';

import 'api_service.dart';

class BrokerAccountsPage extends StatefulWidget {
  const BrokerAccountsPage({
    super.key,
    required this.api,
  });

  final ApiService api;

  @override
  State<BrokerAccountsPage> createState() =>
      _BrokerAccountsPageState();
}

class _BrokerAccountsPageState
    extends State<BrokerAccountsPage> {
  static const gold = Color(0xFFF5B82E);
  static const green = Color(0xFF00E59B);
  static const red = Color(0xFFFF5C6C);
  static const orange = Color(0xFFFFA726);
  static const background = Color(0xFF030B14);
  static const card = Color(0xFF091724);
  static const border = Color(0xFF17334D);
  static const muted = Color(0xFF8EA4B8);

  bool loading = true;
  bool submitting = false;

  String errorMessage = '';

  List<Map<String, dynamic>> accounts = [];

  @override
  void initState() {
    super.initState();
    _loadAccounts();
  }

  Future<void> _loadAccounts() async {
    if (!mounted) return;

    setState(() {
      loading = true;
      errorMessage = '';
    });

    try {
      final response =
          await widget.api.brokerAccounts();

      final rawAccounts =
          response['accounts'];

      final loaded =
          <Map<String, dynamic>>[];

      if (rawAccounts is List) {
        for (final item in rawAccounts) {
          if (item is Map) {
            loaded.add(
              Map<String, dynamic>.from(item),
            );
          }
        }
      }

      if (!mounted) return;

      setState(() {
        accounts = loaded;
        loading = false;
      });
    } catch (error) {
      if (!mounted) return;

      setState(() {
        loading = false;
        errorMessage =
            _friendlyError(error);
      });
    }
  }

  String _friendlyError(Object error) {
    var text = error.toString();

    if (text.startsWith('DioException')) {
      final marker = 'message:';

      final index = text.indexOf(marker);

      if (index >= 0) {
        text =
            text.substring(index + marker.length);
      }
    }

    if (text.length > 220) {
      return text.substring(0, 220);
    }

    return text;
  }

  Future<void> _showAddAccountDialog() async {
    final brokerController =
        TextEditingController(text: 'Exness');

    final platformController =
        TextEditingController(text: 'MT5');

    final serverController =
        TextEditingController();

    final accountNumberController =
        TextEditingController();

    final credentialController =
        TextEditingController();

    bool obscureCredential = true;
    bool dialogSubmitting = false;

    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (
            context,
            setDialogState,
          ) {
            return AlertDialog(
              backgroundColor: card,
              title: const Row(
                children: [
                  Icon(
                    Icons.account_balance,
                    color: gold,
                  ),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Add Broker Account',
                    ),
                  ),
                ],
              ),
              content:
                  SingleChildScrollView(
                child: Column(
                  mainAxisSize:
                      MainAxisSize.min,
                  children: [
                    _dialogField(
                      controller:
                          brokerController,
                      label: 'Broker',
                      hint: 'Exness',
                      icon:
                          Icons.business_outlined,
                    ),
                    const SizedBox(height: 12),
                    _dialogField(
                      controller:
                          platformController,
                      label: 'Platform',
                      hint: 'MT5',
                      icon:
                          Icons.devices_outlined,
                    ),
                    const SizedBox(height: 12),
                    _dialogField(
                      controller:
                          serverController,
                      label: 'MT5 Server',
                      hint:
                          'Example: Exness-MT5Real',
                      icon:
                          Icons.dns_outlined,
                    ),
                    const SizedBox(height: 12),
                    _dialogField(
                      controller:
                          accountNumberController,
                      label:
                          'Account Number',
                      hint:
                          'MT5 account number',
                      icon:
                          Icons.badge_outlined,
                      keyboardType:
                          TextInputType.number,
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller:
                          credentialController,
                      obscureText:
                          obscureCredential,
                      decoration:
                          InputDecoration(
                        labelText:
                            'Credential Reference',
                        hintText:
                            'Secure reference',
                        prefixIcon:
                            const Icon(
                          Icons.key_outlined,
                        ),
                        suffixIcon:
                            IconButton(
                          onPressed: () {
                            setDialogState(() {
                              obscureCredential =
                                  !obscureCredential;
                            });
                          },
                          icon: Icon(
                            obscureCredential
                                ? Icons
                                    .visibility_outlined
                                : Icons
                                    .visibility_off_outlined,
                          ),
                        ),
                        border:
                            const OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    _securityBox(
                      'The credential reference is not the MT5 password. Raymond never stores the MT5 password in the broker-account record.',
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed:
                      dialogSubmitting
                          ? null
                          : () {
                              Navigator.of(
                                dialogContext,
                              ).pop(false);
                            },
                  child:
                      const Text('Cancel'),
                ),
                FilledButton.icon(
                  onPressed:
                      dialogSubmitting
                          ? null
                          : () async {
                              final broker =
                                  brokerController
                                      .text
                                      .trim();

                              final platform =
                                  platformController
                                      .text
                                      .trim();

                              final server =
                                  serverController
                                      .text
                                      .trim();

                              final accountNumber =
                                  accountNumberController
                                      .text
                                      .trim();

                              final credentialRef =
                                  credentialController
                                      .text
                                      .trim();

                              if (broker.isEmpty ||
                                  platform.isEmpty ||
                                  server.isEmpty ||
                                  accountNumber
                                      .isEmpty ||
                                  credentialRef
                                      .isEmpty) {
                                ScaffoldMessenger.of(
                                  dialogContext,
                                ).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                      'Please complete all fields.',
                                    ),
                                  ),
                                );
                                return;
                              }

                              setDialogState(() {
                                dialogSubmitting =
                                    true;
                              });

                              try {
                                await widget.api
                                    .createBrokerAccount(
                                  broker: broker,
                                  platform:
                                      platform,
                                  server: server,
                                  accountNumber:
                                      accountNumber,
                                  credentialRef:
                                      credentialRef,
                                );

                                if (!mounted) {
                                  return;
                                }

                                Navigator.of(
                                  dialogContext,
                                ).pop(true);
                              } catch (error) {
                                setDialogState(() {
                                  dialogSubmitting =
                                      false;
                                });

                                ScaffoldMessenger.of(
                                  dialogContext,
                                ).showSnackBar(
                                  SnackBar(
                                    content:
                                        Text(
                                      _friendlyError(
                                        error,
                                      ),
                                    ),
                                  ),
                                );
                              }
                            },
                  icon: dialogSubmitting
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child:
                              CircularProgressIndicator(
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(
                          Icons.add,
                        ),
                  label:
                      const Text('Add Account'),
                ),
              ],
            );
          },
        );
      },
    );

    brokerController.dispose();
    platformController.dispose();
    serverController.dispose();
    accountNumberController.dispose();
    credentialController.dispose();

    if (result == true) {
      await _loadAccounts();

      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'Broker account added successfully.',
          ),
        ),
      );
    }
  }

  Widget _dialogField({
    required TextEditingController controller,
    required String label,
    required String hint,
    required IconData icon,
    TextInputType? keyboardType,
  }) {
    return TextField(
      controller: controller,
      keyboardType: keyboardType,
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        prefixIcon: Icon(icon),
        border:
            const OutlineInputBorder(),
      ),
    );
  }

  Widget _securityBox(String text) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: gold.withOpacity(.08),
        borderRadius:
            BorderRadius.circular(12),
        border: Border.all(
          color: gold.withOpacity(.25),
        ),
      ),
      child: Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.security,
            color: gold,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                color: muted,
                fontSize: 12,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _showConnectDialog(
    Map<String, dynamic> account,
  ) async {
    final accountId =
        account['account_id']?.toString();

    if (accountId == null ||
        accountId.isEmpty) {
      return;
    }

    final passwordController =
        TextEditingController();

    final terminalPathController =
        TextEditingController();

    bool obscurePassword = true;
    bool dialogSubmitting = false;

    final result =
        await showDialog<Map<String, dynamic>>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        return StatefulBuilder(
          builder: (
            context,
            setDialogState,
          ) {
            return AlertDialog(
              backgroundColor: card,
              title: const Row(
                children: [
                  Icon(
                    Icons.link,
                    color: gold,
                  ),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Connect & Verify MT5',
                    ),
                  ),
                ],
              ),
              content:
                  SingleChildScrollView(
                child: Column(
                  mainAxisSize:
                      MainAxisSize.min,
                  children: [
                    _infoBox(
                      'Account',
                      '${account['broker'] ?? 'Broker'} • ${account['account_number'] ?? 'Unknown'}',
                    ),
                    const SizedBox(height: 12),
                    _infoBox(
                      'Server',
                      account['server']
                              ?.toString() ??
                          'Unknown',
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller:
                          passwordController,
                      obscureText:
                          obscurePassword,
                      autofocus: true,
                      decoration:
                          InputDecoration(
                        labelText:
                            'MT5 Password',
                        hintText:
                            'Enter MT5 trading password',
                        prefixIcon:
                            const Icon(
                          Icons.lock_outline,
                        ),
                        suffixIcon:
                            IconButton(
                          onPressed: () {
                            setDialogState(() {
                              obscurePassword =
                                  !obscurePassword;
                            });
                          },
                          icon: Icon(
                            obscurePassword
                                ? Icons
                                    .visibility_outlined
                                : Icons
                                    .visibility_off_outlined,
                          ),
                        ),
                        border:
                            const OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller:
                          terminalPathController,
                      decoration:
                          const InputDecoration(
                        labelText:
                            'MT5 Terminal Path',
                        hintText:
                            'Optional — normally configured on the server',
                        prefixIcon:
                            Icon(
                          Icons.folder_outlined,
                        ),
                        border:
                            OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    _securityBox(
                      'The MT5 password is sent only for this connection request. Raymond does not save it in the broker account database. A successful connection still does NOT authorize live trading.',
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed:
                      dialogSubmitting
                          ? null
                          : () {
                              Navigator.of(
                                dialogContext,
                              ).pop(null);
                            },
                  child:
                      const Text('Cancel'),
                ),
                FilledButton.icon(
                  onPressed:
                      dialogSubmitting
                          ? null
                          : () async {
                              final password =
                                  passwordController
                                      .text;

                              if (password
                                  .isEmpty) {
                                ScaffoldMessenger.of(
                                  dialogContext,
                                ).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                      'Enter the MT5 password.',
                                    ),
                                  ),
                                );
                                return;
                              }

                              setDialogState(() {
                                dialogSubmitting =
                                    true;
                              });

                              try {
                                final response =
                                    await widget.api
                                        .connectBrokerAccount(
                                  accountId:
                                      accountId,
                                  password:
                                      password,
                                  terminalPath:
                                      terminalPathController
                                          .text
                                          .trim(),
                                );

                                if (!mounted) {
                                  return;
                                }

                                Navigator.of(
                                  dialogContext,
                                ).pop(response);
                              } catch (error) {
                                setDialogState(() {
                                  dialogSubmitting =
                                      false;
                                });

                                ScaffoldMessenger.of(
                                  dialogContext,
                                ).showSnackBar(
                                  SnackBar(
                                    content:
                                        Text(
                                      _friendlyError(
                                        error,
                                      ),
                                    ),
                                  ),
                                );
                              }
                            },
                  icon: dialogSubmitting
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child:
                              CircularProgressIndicator(
                            strokeWidth: 2,
                          ),
                        )
                      : const Icon(
                          Icons.link,
                        ),
                  label:
                      const Text('Connect'),
                ),
              ],
            );
          },
        );
      },
    );

    passwordController.dispose();
    terminalPathController.dispose();

    if (result != null) {
      await _loadAccounts();

      if (!mounted) return;

      _showConnectionResult(result);
    }
  }

  Widget _infoBox(
    String label,
    String value,
  ) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: background,
        borderRadius:
            BorderRadius.circular(10),
        border: Border.all(
          color: border,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(
              color: muted,
              fontSize: 11,
            ),
          ),
          const SizedBox(height: 3),
          Text(
            value,
            style: const TextStyle(
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }

  void _showConnectionResult(
    Map<String, dynamic> result,
  ) {
    final status =
        result['status']?.toString() ??
            'unknown';

    final verificationRaw =
        result['verification'];

    final verification =
        verificationRaw is Map
            ? Map<String, dynamic>.from(
                verificationRaw,
              )
            : <String, dynamic>{};

    final verified =
        verification['account_verified'] ==
            true;

    final tradingAllowed =
        verification['trading_allowed'] ==
            true;

    final liveAuthorization =
        result['live_authorization'] ==
            true;

    showDialog<void>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: card,
          title: Row(
            children: [
              Icon(
                verified
                    ? Icons.verified
                    : Icons.warning_amber_rounded,
                color:
                    verified ? green : orange,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  verified
                      ? 'MT5 Verified'
                      : 'Verification Failed',
                ),
              ),
            ],
          ),
          content:
              SingleChildScrollView(
            child: Column(
              crossAxisAlignment:
                  CrossAxisAlignment.start,
              children: [
                _resultRow(
                  'Connection',
                  status,
                  verified
                      ? green
                      : red,
                ),
                _resultRow(
                  'Terminal connected',
                  _yesNo(
                    verification[
                        'terminal_connected'],
                  ),
                  _boolColor(
                    verification[
                        'terminal_connected'],
                  ),
                ),
                _resultRow(
                  'Account number',
                  _yesNo(
                    verification[
                        'account_number_matches'],
                  ),
                  _boolColor(
                    verification[
                        'account_number_matches'],
                  ),
                ),
                _resultRow(
                  'Server',
                  _yesNo(
                    verification[
                        'server_matches'],
                  ),
                  _boolColor(
                    verification[
                        'server_matches'],
                  ),
                ),
                _resultRow(
                  'Trading allowed',
                  tradingAllowed
                      ? 'YES'
                      : 'NO',
                  tradingAllowed
                      ? green
                      : orange,
                ),
                _resultRow(
                  'Live authorization',
                  liveAuthorization
                      ? 'AUTHORIZED'
                      : 'DISABLED',
                  liveAuthorization
                      ? red
                      : green,
                ),
                const SizedBox(height: 14),
                _securityBox(
                  'Order created: ${result['order_created'] == true ? 'YES' : 'NO'}. Connection verification never creates a trade.',
                ),
              ],
            ),
          ),
          actions: [
            FilledButton(
              onPressed: () =>
                  Navigator.pop(context),
              child: const Text('Done'),
            ),
          ],
        );
      },
    );
  }

  Widget _resultRow(
    String label,
    String value,
    Color color,
  ) {
    return Padding(
      padding:
          const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(
                color: muted,
                fontSize: 12,
              ),
            ),
          ),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight:
                  FontWeight.w800,
            ),
          ),
        ],
      ),
    );
  }

  String _yesNo(dynamic value) {
    return value == true ? 'YES' : 'NO';
  }

  Color _boolColor(dynamic value) {
    return value == true ? green : red;
  }

  Future<void> _disconnectAccount(
    Map<String, dynamic> account,
  ) async {
    final accountId =
        account['account_id']?.toString();

    if (accountId == null ||
        accountId.isEmpty) {
      return;
    }

    final confirmed =
        await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: card,
          title: const Text(
            'Disconnect MT5?',
          ),
          content: const Text(
            'Raymond will disconnect its MT5 session. This does not close broker positions.',
          ),
          actions: [
            TextButton(
              onPressed: () =>
                  Navigator.pop(
                context,
                false,
              ),
              child:
                  const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () =>
                  Navigator.pop(
                context,
                true,
              ),
              child:
                  const Text('Disconnect'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    setState(() {
      submitting = true;
    });

    try {
      await widget.api
          .disconnectBrokerAccount(
        accountId,
      );

      await _loadAccounts();

      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'MT5 account disconnected. No broker position was closed.',
          ),
        ),
      );
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        SnackBar(
          content: Text(
            _friendlyError(error),
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> _selectAccount(
    Map<String, dynamic> account,
  ) async {
    final accountId =
        account['account_id']?.toString();

    if (accountId == null ||
        accountId.isEmpty) {
      return;
    }

    setState(() {
      submitting = true;
    });

    try {
      await widget.api
          .selectBrokerAccount(accountId);

      await _loadAccounts();

      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'Broker account selected. Live authorization remains disabled.',
          ),
        ),
      );
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        SnackBar(
          content: Text(
            _friendlyError(error),
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> _disableLive(
    Map<String, dynamic> account,
  ) async {
    final accountId =
        account['account_id']?.toString();

    if (accountId == null ||
        accountId.isEmpty) {
      return;
    }

    setState(() {
      submitting = true;
    });

    try {
      await widget.api
          .disableBrokerLive(accountId);

      await _loadAccounts();

      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content: Text(
            'Live trading authorization disabled.',
          ),
        ),
      );
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        SnackBar(
          content: Text(
            _friendlyError(error),
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  Future<void> _deleteAccount(
    Map<String, dynamic> account,
  ) async {
    final accountId =
        account['account_id']?.toString();

    if (accountId == null ||
        accountId.isEmpty) {
      return;
    }

    final confirmed =
        await showDialog<bool>(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: card,
          title:
              const Text('Delete account?'),
          content: const Text(
            'This removes the broker account record from Raymond. A selected account cannot be deleted.',
          ),
          actions: [
            TextButton(
              onPressed: () =>
                  Navigator.pop(
                context,
                false,
              ),
              child:
                  const Text('Cancel'),
            ),
            FilledButton(
              style:
                  FilledButton.styleFrom(
                backgroundColor: red,
              ),
              onPressed: () =>
                  Navigator.pop(
                context,
                true,
              ),
              child:
                  const Text('Delete'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) {
      return;
    }

    setState(() {
      submitting = true;
    });

    try {
      await widget.api
          .deleteBrokerAccount(accountId);

      await _loadAccounts();

      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        const SnackBar(
          content:
              Text('Broker account deleted.'),
        ),
      );
    } catch (error) {
      if (!mounted) return;

      ScaffoldMessenger.of(context)
          .showSnackBar(
        SnackBar(
          content: Text(
            _friendlyError(error),
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          submitting = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: background,
      appBar: AppBar(
        backgroundColor: background,
        elevation: 0,
        title: const Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            Text(
              'Broker Accounts',
              style: TextStyle(
                fontWeight:
                    FontWeight.w800,
              ),
            ),
            Text(
              'Demo / Live MT5 connection',
              style: TextStyle(
                color: muted,
                fontSize: 11,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            onPressed:
                loading
                    ? null
                    : _loadAccounts,
            icon: const Icon(
              Icons.refresh,
            ),
          ),
        ],
      ),
      floatingActionButton:
          FloatingActionButton.extended(
        backgroundColor: gold,
        foregroundColor: Colors.black,
        onPressed:
            submitting
                ? null
                : _showAddAccountDialog,
        icon:
            const Icon(Icons.add),
        label: const Text(
          'Add Broker',
          style: TextStyle(
            fontWeight:
                FontWeight.bold,
          ),
        ),
      ),
      body: RefreshIndicator(
        onRefresh: _loadAccounts,
        child: loading
            ? const Center(
                child:
                    CircularProgressIndicator(
                  color: gold,
                ),
              )
            : _buildContent(),
      ),
    );
  }

  Widget _buildContent() {
    if (errorMessage.isNotEmpty &&
        accounts.isEmpty) {
      return ListView(
        physics:
            const AlwaysScrollableScrollPhysics(),
        padding:
            const EdgeInsets.all(20),
        children: [
          _errorCard(),
        ],
      );
    }

    if (accounts.isEmpty) {
      return ListView(
        physics:
            const AlwaysScrollableScrollPhysics(),
        padding:
            const EdgeInsets.all(20),
        children: [
          _introCard(),
          const SizedBox(height: 20),
          _emptyCard(),
        ],
      );
    }

    return ListView(
      physics:
          const AlwaysScrollableScrollPhysics(),
      padding:
          const EdgeInsets.fromLTRB(
        16,
        12,
        16,
        100,
      ),
      children: [
        _securityBanner(),
        const SizedBox(height: 16),
        Text(
          '${accounts.length} broker account${accounts.length == 1 ? '' : 's'}',
          style: const TextStyle(
            color: muted,
            fontSize: 13,
            fontWeight:
                FontWeight.w600,
          ),
        ),
        const SizedBox(height: 10),
        ...accounts.map(
          _accountCard,
        ),
      ],
    );
  }

  Widget _introCard() {
    return Container(
      padding:
          const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(18),
        border: Border.all(
          color: border,
        ),
      ),
      child: const Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.account_balance_wallet,
            color: gold,
            size: 32,
          ),
          SizedBox(height: 12),
          Text(
            'Connect your broker',
            style: TextStyle(
              fontSize: 20,
              fontWeight:
                  FontWeight.w800,
            ),
          ),
          SizedBox(height: 8),
          Text(
            'Add your MT5 broker account, then use Connect & Verify to test the account and terminal connection.',
            style: TextStyle(
              color: muted,
              height: 1.5,
            ),
          ),
        ],
      ),
    );
  }

  Widget _securityBanner() {
    return Container(
      padding:
          const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: gold.withOpacity(.07),
        borderRadius:
            BorderRadius.circular(14),
        border: Border.all(
          color: gold.withOpacity(.25),
        ),
      ),
      child: const Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Icon(
            Icons.shield_outlined,
            color: gold,
          ),
          SizedBox(width: 10),
          Expanded(
            child: Text(
              'Connection and verification are separate from live authorization. Raymond can connect to MT5 without creating an order. Live execution remains fail-closed.',
              style: TextStyle(
                color: muted,
                fontSize: 12,
                height: 1.45,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _emptyCard() {
    return Container(
      padding:
          const EdgeInsets.all(30),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(18),
        border: Border.all(
          color: border,
        ),
      ),
      child: const Column(
        children: [
          Icon(
            Icons.link_off,
            color: muted,
            size: 44,
          ),
          SizedBox(height: 14),
          Text(
            'No broker accounts',
            style: TextStyle(
              fontSize: 18,
              fontWeight:
                  FontWeight.w700,
            ),
          ),
          SizedBox(height: 6),
          Text(
            'Add an MT5 account to begin broker configuration.',
            textAlign:
                TextAlign.center,
            style: TextStyle(
              color: muted,
            ),
          ),
        ],
      ),
    );
  }

  Widget _errorCard() {
    return Container(
      padding:
          const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: red.withOpacity(.07),
        borderRadius:
            BorderRadius.circular(16),
        border: Border.all(
          color: red.withOpacity(.3),
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.error_outline,
            color: red,
          ),
          const SizedBox(height: 10),
          const Text(
            'Unable to load broker accounts',
            style: TextStyle(
              fontWeight:
                  FontWeight.bold,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            errorMessage,
            style: const TextStyle(
              color: muted,
              fontSize: 12,
            ),
          ),
          const SizedBox(height: 14),
          FilledButton.icon(
            onPressed:
                _loadAccounts,
            icon:
                const Icon(Icons.refresh),
            label:
                const Text('Retry'),
          ),
        ],
      ),
    );
  }

  Widget _accountCard(
    Map<String, dynamic> account,
  ) {
    final selected =
        account['selected'] == true;

    final verified =
        account['account_verified'] ==
            true;

    final tradingAllowed =
        account['trading_allowed'] ==
            true;

    final liveAuthorized =
        account[
                'live_trading_authorized'] ==
            true;

    final connection =
        account[
                    'connection_status']
                ?.toString() ??
            'disconnected';

    final broker =
        account['broker']?.toString() ??
            'Unknown broker';

    final platform =
        account['platform']?.toString() ??
            'MT5';

    final server =
        account['server']?.toString() ??
            'Unknown server';

    final accountNumber =
        account[
                    'account_number']
                ?.toString() ??
            '****';

    final balance =
        account['balance'];

    final equity =
        account['equity'];

    final lastError =
        account['last_error']
                ?.toString() ??
            '';

    return Container(
      margin:
          const EdgeInsets.only(
        bottom: 14,
      ),
      padding:
          const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: card,
        borderRadius:
            BorderRadius.circular(18),
        border: Border.all(
          color: selected
              ? gold.withOpacity(.65)
              : border,
          width:
              selected ? 1.4 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 46,
                height: 46,
                decoration:
                    BoxDecoration(
                  color:
                      gold.withOpacity(.1),
                  borderRadius:
                      BorderRadius.circular(
                    14,
                  ),
                ),
                child: const Icon(
                  Icons.account_balance,
                  color: gold,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            broker,
                            style:
                                const TextStyle(
                              fontSize: 17,
                              fontWeight:
                                  FontWeight.w800,
                            ),
                          ),
                        ),
                        if (selected) ...[
                          const SizedBox(
                            width: 8,
                          ),
                          _statusChip(
                            'SELECTED',
                            gold,
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '$platform • $accountNumber',
                      style:
                          const TextStyle(
                        color: muted,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          _infoRow(
            Icons.dns_outlined,
            'Server',
            server,
          ),
          _infoRow(
            Icons.wifi,
            'Connection',
            connection.toUpperCase(),
            valueColor:
                connection == 'connected'
                    ? green
                    : connection ==
                            'error'
                        ? red
                        : muted,
          ),
          _infoRow(
            Icons.verified_outlined,
            'Account verified',
            verified ? 'YES' : 'NO',
            valueColor:
                verified ? green : muted,
          ),
          _infoRow(
            Icons.lock_outline,
            'Trading allowed',
            tradingAllowed
                ? 'YES'
                : 'NO',
            valueColor:
                tradingAllowed
                    ? green
                    : orange,
          ),
          _infoRow(
            Icons.shield_outlined,
            'Live authorization',
            liveAuthorized
                ? 'AUTHORIZED'
                : 'DISABLED',
            valueColor:
                liveAuthorized
                    ? red
                    : green,
          ),
          if (balance is num)
            _infoRow(
              Icons
                  .account_balance_wallet_outlined,
              'Balance',
              _money(balance),
            ),
          if (equity is num)
            _infoRow(
              Icons.show_chart,
              'Equity',
              _money(equity),
            ),
          if (lastError.isNotEmpty)
            _errorInline(lastError),
          const SizedBox(height: 14),
          const Divider(
            color: border,
          ),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.icon(
                onPressed:
                    submitting
                        ? null
                        : () =>
                            _showConnectDialog(
                              account,
                            ),
                icon: Icon(
                  verified
                      ? Icons.refresh
                      : Icons.link,
                ),
                label: Text(
                  verified
                      ? 'Reconnect'
                      : 'Connect & Verify',
                ),
              ),
              if (connection ==
                      'connected' ||
                  verified)
                OutlinedButton.icon(
                  onPressed:
                      submitting
                          ? null
                          : () =>
                              _disconnectAccount(
                                account,
                              ),
                  icon: const Icon(
                    Icons.link_off,
                  ),
                  label:
                      const Text('Disconnect'),
                ),
              if (!selected)
                OutlinedButton.icon(
                  onPressed:
                      submitting
                          ? null
                          : () =>
                              _selectAccount(
                                account,
                              ),
                  icon: const Icon(
                    Icons
                        .check_circle_outline,
                  ),
                  label:
                      const Text('Select'),
                ),
              OutlinedButton.icon(
                onPressed:
                    submitting
                        ? null
                        : () =>
                            _disableLive(
                              account,
                            ),
                icon: const Icon(
                  Icons.lock_outline,
                ),
                label:
                    const Text('Disable Live'),
              ),
              OutlinedButton.icon(
                style:
                    OutlinedButton.styleFrom(
                  foregroundColor: red,
                  side: BorderSide(
                    color:
                        red.withOpacity(.4),
                  ),
                ),
                onPressed:
                    submitting
                        ? null
                        : () =>
                            _deleteAccount(
                              account,
                            ),
                icon: const Icon(
                  Icons.delete_outline,
                ),
                label:
                    const Text('Delete'),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _errorInline(String text) {
    return Container(
      width: double.infinity,
      margin:
          const EdgeInsets.only(top: 4),
      padding:
          const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: red.withOpacity(.06),
        borderRadius:
            BorderRadius.circular(10),
        border: Border.all(
          color: red.withOpacity(.2),
        ),
      ),
      child: Row(
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.error_outline,
            color: red,
            size: 17,
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(
                color: muted,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusChip(
    String text,
    Color color,
  ) {
    return Container(
      padding:
          const EdgeInsets.symmetric(
        horizontal: 7,
        vertical: 3,
      ),
      decoration:
          BoxDecoration(
        color:
            color.withOpacity(.12),
        borderRadius:
            BorderRadius.circular(8),
        border: Border.all(
          color:
              color.withOpacity(.3),
        ),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 9,
          fontWeight:
              FontWeight.w800,
        ),
      ),
    );
  }

  Widget _infoRow(
    IconData icon,
    String label,
    String value, {
    Color valueColor = Colors.white,
  }) {
    return Padding(
      padding:
          const EdgeInsets.only(
        bottom: 9,
      ),
      child: Row(
        children: [
          Icon(
            icon,
            size: 17,
            color: muted,
          ),
          const SizedBox(width: 9),
          Text(
            label,
            style: const TextStyle(
              color: muted,
              fontSize: 12,
            ),
          ),
          const Spacer(),
          Flexible(
            child: Text(
              value,
              textAlign:
                  TextAlign.right,
              style: TextStyle(
                color: valueColor,
                fontSize: 12,
                fontWeight:
                    FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _money(Object value) {
    if (value is num) {
      return '\$${value.toStringAsFixed(2)}';
    }

    return value.toString();
  }
}
