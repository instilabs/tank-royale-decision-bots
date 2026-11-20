import dev.robocode.tankroyale.runner.*;
import java.time.Duration;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

// 4-way melee, one command. Usage: java -cp robocode-tankroyale-runner-1.4.0.jar RunMelee.java <dir1> <dir2> <dir3> <dir4> [rounds]
public class RunMelee {
    public static void main(String[] args) {
        Logger.getLogger("dev.robocode.tankroyale").setLevel(Level.WARNING);
        int rounds = args.length > 4 ? Integer.parseInt(args[4]) : 5;
        try (var runner = BattleRunner.create(b -> {
            b.embeddedServer();
            b.botConnectTimeout(Duration.ofSeconds(60));
        })) {
            var setup = BattleSetup.melee(s -> s.setNumberOfRounds(rounds));
            var bots = List.of(BotEntry.of(args[0]), BotEntry.of(args[1]),
                               BotEntry.of(args[2]), BotEntry.of(args[3]));
            var results = runner.runBattle(setup, bots);
            for (var bot : results.getResults())
                System.out.printf("RESULT rank=%d name=%s score=%d%n",
                    bot.getRank(), bot.getName(), bot.getTotalScore());
        }
    }
}
