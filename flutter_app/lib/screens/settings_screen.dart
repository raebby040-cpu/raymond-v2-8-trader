import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/settings_provider.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({Key? key}) : super(key: key);

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<SettingsProvider>().init();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        elevation: 0,
      ),
      body: Consumer<SettingsProvider>(
        builder: (context, settings, _) {
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const Text(
                'API Configuration',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              TextField(
                decoration: const InputDecoration(
                  labelText: 'API URL',
                  border: OutlineInputBorder(),
                ),
                controller: TextEditingController(text: settings.apiUrl),
                onChanged: (value) => settings.setApiUrl(value),
              ),
              const SizedBox(height: 20),
              const Text(
                'Broker Settings',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: settings.broker,
                decoration: const InputDecoration(
                  labelText: 'Broker',
                  border: OutlineInputBorder(),
                ),
                items: const [
                  DropdownMenuItem(value: 'mt5', child: Text('MetaTrader 5')),
                  DropdownMenuItem(value: 'exness', child: Text('Exness')),
                ],
                onChanged: (value) => settings.setBroker(value ?? 'mt5'),
              ),
              const SizedBox(height: 20),
              const Text(
                'Safety Settings',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                title: const Text('Live Trading'),
                subtitle: const Text('Enable live order execution (DANGEROUS)'),
                value: settings.liveTrading,
                onChanged: (value) {
                  if (value) {
                    showDialog(
                      context: context,
                      builder: (context) => AlertDialog(
                        title: const Text('Warning'),
                        content: const Text('Live trading is ENABLED. You may lose real money.'),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(context),
                            child: const Text('Cancel'),
                          ),
                          TextButton(
                            onPressed: () {
                              settings.setLiveTrading(true);
                              Navigator.pop(context);
                            },
                            child: const Text('Enable'),
                          ),
                        ],
                      ),
                    );
                  } else {
                    settings.setLiveTrading(false);
                  }
                },
              ),
              const SizedBox(height: 20),
              const Text(
                'Display Settings',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              SwitchListTile(
                title: const Text('Dark Mode'),
                value: settings.darkMode,
                onChanged: (value) => settings.setDarkMode(value),
              ),
              const SizedBox(height: 40),
              Text(
                'RAYMOND v2.8.0\nBuilt with Flutter',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          );
        },
      ),
    );
  }
}
