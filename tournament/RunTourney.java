import dev.robocode.tankroyale.runner.*;
import java.time.Duration;
import java.util.List;
import java.util.logging.Level;
import java.util.logging.Logger;

// Usage: java -cp robocode-tankroyale-runner-1.4.0.jar RunTourney.java <botDir1> <botDir2> [rounds]
public class RunTourney {
    public static void main(String[] args) {
        Logger.getLogger("dev.robocode.tankroyale").setLevel(Level.INFO);
        int rounds = args.length > 2 ? Integer.parseInt(args[2]) : 3;
        try (var runner = BattleRunner.create(b -> {
            b.embeddedServer();
            b.botConnectTimeout(Duration.ofSeconds(60));
        })) {
            var setup = BattleSetup.classic(s -> s.setNumberOfRounds(rounds));
            var bots = List.of(BotEntry.of(args[0]), BotEntry.of(args[1]));
            var results = runner.runBattle(setup, bots);
            for (var bot : results.getResults())
                System.out.printf("RESULT rank=%d name=%s score=%d%n",
                    bot.getRank(), bot.getName(), bot.getTotalScore());
        }
    }
}
